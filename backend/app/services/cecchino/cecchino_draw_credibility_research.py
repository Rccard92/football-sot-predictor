"""Audit storico copertura dati Credibilità X — modulo ricerca offline (Fase 1A)."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_FINISHED,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_betfair_odds_payload import build_betfair_payload_from_snapshot
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_goal_formulas import goal_market_kpi_entry
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import normalize_kpi_panel_rows
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_OU,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)
from app.services.cecchino.cecchino_signal_goal_refs import resolve_under_2_5_cecchino_odd

VERSION = "cecchino_draw_credibility_research_v1"

_EXCLUSION_REASONS = (
    "not_finished",
    "missing_fulltime_result",
    "unsupported_payload_version",
    "missing_cecchino_final",
    "missing_cecchino_1x2_odds",
    "missing_cecchino_1x2_probabilities",
    "missing_cecchino_under_2_5",
    "missing_cecchino_over_2_5",
    "missing_book_1x2",
    "missing_book_under_2_5",
    "missing_book_over_2_5",
    "invalid_numeric_value",
)

_MAX_DEBUG_SAMPLES = 20


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_cecchino_odd(odd: float | None) -> bool:
    return odd is not None and math.isfinite(odd) and odd > 0


def _valid_book_odd(odd: float | None) -> bool:
    return odd is not None and math.isfinite(odd) and odd > 1


def _pct(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return round(100.0 * n / d, 2)


def _resolve_fulltime_score(row: CecchinoTodayFixture) -> tuple[int | None, int | None]:
    if row.match_display_status != MATCH_FINISHED:
        return None, None
    home = row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home
    away = row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away
    if home is None or away is None:
        return None, None
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None, None


def _kpi_panel_cecchino_odd(kpi_panel: dict | None, market_key: str, labels: tuple[str, ...]) -> float | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == market_key:
            odd = _num(row.get("quota_cecchino"))
            if _valid_cecchino_odd(odd):
                return odd
        label = str(row.get("segno") or row.get("label") or "").strip().lower()
        if label in labels:
            odd = _num(row.get("quota_cecchino"))
            if _valid_cecchino_odd(odd):
                return odd
    return None


def _resolve_over_2_5_cecchino_odd(
    *,
    kpi_panel: dict | None = None,
    goal_markets: dict | None = None,
) -> float | None:
    odd = _kpi_panel_cecchino_odd(
        kpi_panel,
        SEL_OVER_2_5,
        ("over 2.5", "over2.5", "o2.5"),
    )
    if _valid_cecchino_odd(odd):
        return odd
    if isinstance(goal_markets, dict):
        q, _, _ = goal_market_kpi_entry(goal_markets, SEL_OVER_2_5)
        if _valid_cecchino_odd(q):
            return q
    return None


def _kpi_panel_book_odd(kpi_panel: dict | None, market_key: str) -> float | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == market_key:
            odd = _num(row.get("quota_book"))
            if _valid_book_odd(odd):
                return odd
    return None


def _snapshot_book_odds(
    odds_snapshot: dict[str, Any] | None,
    *,
    home_team_name: str | None,
    away_team_name: str | None,
) -> dict[str, float | None]:
    payload = build_betfair_payload_from_snapshot(
        odds_snapshot,
        source="cached_betfair_odds",
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )
    out: dict[str, float | None] = {
        SEL_HOME: None,
        SEL_DRAW: None,
        SEL_AWAY: None,
        SEL_UNDER_2_5: None,
        SEL_OVER_2_5: None,
    }
    for bm in payload.get("bookmakers") or []:
        if not isinstance(bm, dict) or bm.get("status") != "available":
            continue
        markets = bm.get("markets") or {}
        m1x2 = markets.get(MARKET_1X2) or {}
        ou = markets.get(MARKET_OU) or {}
        if isinstance(m1x2, dict):
            for sk in (SEL_HOME, SEL_DRAW, SEL_AWAY):
                if out[sk] is None:
                    out[sk] = _num(m1x2.get(sk))
        if isinstance(ou, dict):
            for sk in (SEL_UNDER_2_5, SEL_OVER_2_5):
                if out[sk] is None:
                    out[sk] = _num(ou.get(sk))
    return out


def _resolve_book_odd(
    *,
    market_key: str,
    kpi_panel: dict | None,
    odds_snapshot: dict[str, Any] | None,
    home_team_name: str | None,
    away_team_name: str | None,
    snapshot_cache: dict[str, float | None] | None,
) -> tuple[float | None, str]:
    odd = _kpi_panel_book_odd(kpi_panel, market_key)
    if _valid_book_odd(odd):
        return odd, "kpi_panel"
    snap = snapshot_cache
    if snap is None:
        snap = _snapshot_book_odds(
            odds_snapshot,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )
    odd = snap.get(market_key)
    if _valid_book_odd(odd):
        return odd, "odds_snapshot"
    return None, "missing"


def _cecchino_final(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return None
    final = output.get("final")
    if not isinstance(final, dict):
        return None
    return final


def _evaluate_fixture(row: CecchinoTodayFixture) -> dict[str, Any]:
    kpi_raw = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    kpi_panel = normalize_kpi_panel_rows(kpi_raw) if kpi_raw else None
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else None
    goal_markets = (output or {}).get("goal_markets") if isinstance(output, dict) else None
    final = _cecchino_final(row)

    finished = row.match_display_status == MATCH_FINISHED
    ft_home, ft_away = _resolve_fulltime_score(row)
    has_result = finished and ft_home is not None and ft_away is not None
    is_draw = has_result and ft_home == ft_away

    has_invalid_numeric = False
    if final is not None:
        for key in ("quota_1", "quota_x", "quota_2", "prob_1", "prob_x", "prob_2"):
            raw = final.get(key)
            if raw is not None:
                val = _num(raw)
                if val is None or not math.isfinite(val):
                    has_invalid_numeric = True
                    break

    has_cecchino_final = final is not None and final.get("status") == STATUS_AVAILABLE
    q1 = _num(final.get("quota_1")) if final else None
    qx = _num(final.get("quota_x")) if final else None
    q2 = _num(final.get("quota_2")) if final else None
    p1 = _num(final.get("prob_1")) if final else None
    px = _num(final.get("prob_x")) if final else None
    p2 = _num(final.get("prob_2")) if final else None

    has_1x2_odds = _valid_cecchino_odd(q1) and _valid_cecchino_odd(qx) and _valid_cecchino_odd(q2)
    has_1x2_prob = _valid_cecchino_odd(p1) and _valid_cecchino_odd(px) and _valid_cecchino_odd(p2)
    has_complete_1x2 = has_1x2_odds and has_1x2_prob

    under_odd = resolve_under_2_5_cecchino_odd(kpi_panel=kpi_panel, goal_markets=goal_markets)
    over_odd = _resolve_over_2_5_cecchino_odd(kpi_panel=kpi_panel, goal_markets=goal_markets)
    has_under = _valid_cecchino_odd(under_odd)
    has_over = _valid_cecchino_odd(over_odd)
    has_complete_goal_pair = has_under and has_over

    snapshot_cache = _snapshot_book_odds(
        row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
    )
    book_home, _ = _resolve_book_odd(
        market_key=SEL_HOME,
        kpi_panel=kpi_panel,
        odds_snapshot=row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        snapshot_cache=snapshot_cache,
    )
    book_draw, _ = _resolve_book_odd(
        market_key=SEL_DRAW,
        kpi_panel=kpi_panel,
        odds_snapshot=row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        snapshot_cache=snapshot_cache,
    )
    book_away, _ = _resolve_book_odd(
        market_key=SEL_AWAY,
        kpi_panel=kpi_panel,
        odds_snapshot=row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        snapshot_cache=snapshot_cache,
    )
    book_under, _ = _resolve_book_odd(
        market_key=SEL_UNDER_2_5,
        kpi_panel=kpi_panel,
        odds_snapshot=row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        snapshot_cache=snapshot_cache,
    )
    book_over, _ = _resolve_book_odd(
        market_key=SEL_OVER_2_5,
        kpi_panel=kpi_panel,
        odds_snapshot=row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        snapshot_cache=snapshot_cache,
    )

    has_book_1x2 = (
        _valid_book_odd(book_home)
        and _valid_book_odd(book_draw)
        and _valid_book_odd(book_away)
    )
    has_book_under = _valid_book_odd(book_under)
    has_book_over = _valid_book_odd(book_over)
    has_complete_book_goal_pair = has_book_under and has_book_over
    has_complete_book_markets = has_book_1x2 and has_complete_book_goal_pair

    usable_internal = (
        has_result
        and has_complete_1x2
        and has_complete_goal_pair
    )
    usable_market = usable_internal and has_complete_book_markets

    primary_reason = _primary_exclusion_reason(
        finished=finished,
        has_result=has_result,
        output=output,
        final=final,
        has_invalid_numeric=has_invalid_numeric,
        has_cecchino_final=has_cecchino_final,
        has_1x2_odds=has_1x2_odds,
        has_1x2_prob=has_1x2_prob,
        has_under=has_under,
        has_over=has_over,
        has_book_1x2=has_book_1x2,
        has_book_under=has_book_under,
        has_book_over=has_book_over,
        usable_internal=usable_internal,
        usable_market=usable_market,
    )

    return {
        "finished": finished,
        "has_result": has_result,
        "is_draw": is_draw,
        "has_1x2_odds": has_1x2_odds,
        "has_1x2_prob": has_1x2_prob,
        "has_complete_1x2": has_complete_1x2,
        "has_under": has_under,
        "has_over": has_over,
        "has_complete_goal_pair": has_complete_goal_pair,
        "has_book_1x2": has_book_1x2,
        "has_book_under": has_book_under,
        "has_book_over": has_book_over,
        "has_complete_book_goal_pair": has_complete_book_goal_pair,
        "has_complete_book_markets": has_complete_book_markets,
        "usable_internal": usable_internal,
        "usable_market": usable_market,
        "primary_reason": primary_reason,
        "league_key": (
            row.competition_id,
            row.country_name or "",
            row.league_name or "",
        ),
        "month": row.scan_date.strftime("%Y-%m") if row.scan_date else "",
    }


def _primary_exclusion_reason(
    *,
    finished: bool,
    has_result: bool,
    output: dict[str, Any] | None,
    final: dict[str, Any] | None,
    has_invalid_numeric: bool,
    has_cecchino_final: bool,
    has_1x2_odds: bool,
    has_1x2_prob: bool,
    has_under: bool,
    has_over: bool,
    has_book_1x2: bool,
    has_book_under: bool,
    has_book_over: bool,
    usable_internal: bool,
    usable_market: bool,
) -> str | None:
    if usable_market:
        return None
    if has_invalid_numeric and finished and has_result:
        return "invalid_numeric_value"
    if not finished:
        return "not_finished"
    if not has_result:
        return "missing_fulltime_result"
    if output is None or final is None:
        return "unsupported_payload_version"
    if not has_cecchino_final:
        return "missing_cecchino_final"
    if not has_1x2_odds:
        return "missing_cecchino_1x2_odds"
    if not has_1x2_prob:
        return "missing_cecchino_1x2_probabilities"
    if not has_under:
        return "missing_cecchino_under_2_5"
    if not has_over:
        return "missing_cecchino_over_2_5"
    if usable_internal and not has_book_1x2:
        return "missing_book_1x2"
    if usable_internal and not has_book_under:
        return "missing_book_under_2_5"
    if usable_internal and not has_book_over:
        return "missing_book_over_2_5"
    return None


def _fixtures_in_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    only_eligible: bool,
) -> list[CecchinoTodayFixture]:
    clauses = [
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
    ]
    if competition_id is not None:
        clauses.append(CecchinoTodayFixture.competition_id == competition_id)
    if only_eligible:
        clauses.append(CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE)
    return list(db.scalars(select(CecchinoTodayFixture).where(*clauses)).all())


def _debug_sample(row: CecchinoTodayFixture, reason: str) -> dict[str, Any]:
    return {
        "today_fixture_id": row.id,
        "provider_fixture_id": row.provider_fixture_id,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "league_name": row.league_name,
        "reason": reason,
    }


def build_draw_credibility_coverage_audit(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    only_eligible: bool = True,
) -> dict[str, Any]:
    fixtures = _fixtures_in_range(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        only_eligible=only_eligible,
    )

    total = len(fixtures)
    eligible = total if only_eligible else sum(
        1 for f in fixtures if f.eligibility_status == ELIGIBILITY_ELIGIBLE
    )

    counts = {
        "finished_fixtures": 0,
        "finished_with_result": 0,
        "draw_results": 0,
        "non_draw_results": 0,
        "with_cecchino_1x2_odds": 0,
        "with_cecchino_1x2_probabilities": 0,
        "with_complete_cecchino_1x2": 0,
        "with_cecchino_under_2_5": 0,
        "with_cecchino_over_2_5": 0,
        "with_complete_cecchino_goal_pair": 0,
        "with_book_1x2": 0,
        "with_book_under_2_5": 0,
        "with_book_over_2_5": 0,
        "with_complete_book_goal_pair": 0,
        "with_complete_book_markets": 0,
        "usable_internal_research": 0,
        "usable_market_comparison": 0,
    }

    reason_counts: dict[str, int] = {r: 0 for r in _EXCLUSION_REASONS}
    debug_by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)

    league_agg: dict[tuple[Any, ...], dict[str, Any]] = {}
    month_agg: dict[str, dict[str, Any]] = {}

    for row in fixtures:
        ev = _evaluate_fixture(row)

        if ev["finished"]:
            counts["finished_fixtures"] += 1
        if ev["has_result"]:
            counts["finished_with_result"] += 1
            if ev["is_draw"]:
                counts["draw_results"] += 1
            else:
                counts["non_draw_results"] += 1
        if ev["has_1x2_odds"]:
            counts["with_cecchino_1x2_odds"] += 1
        if ev["has_1x2_prob"]:
            counts["with_cecchino_1x2_probabilities"] += 1
        if ev["has_complete_1x2"]:
            counts["with_complete_cecchino_1x2"] += 1
        if ev["has_under"]:
            counts["with_cecchino_under_2_5"] += 1
        if ev["has_over"]:
            counts["with_cecchino_over_2_5"] += 1
        if ev["has_complete_goal_pair"]:
            counts["with_complete_cecchino_goal_pair"] += 1
        if ev["has_book_1x2"]:
            counts["with_book_1x2"] += 1
        if ev["has_book_under"]:
            counts["with_book_under_2_5"] += 1
        if ev["has_book_over"]:
            counts["with_book_over_2_5"] += 1
        if ev["has_complete_book_goal_pair"]:
            counts["with_complete_book_goal_pair"] += 1
        if ev["has_complete_book_markets"]:
            counts["with_complete_book_markets"] += 1
        if ev["usable_internal"]:
            counts["usable_internal_research"] += 1
        if ev["usable_market"]:
            counts["usable_market_comparison"] += 1

        reason = ev["primary_reason"]
        if reason is not None:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if len(debug_by_reason[reason]) < _MAX_DEBUG_SAMPLES:
                debug_by_reason[reason].append(_debug_sample(row, reason))

        lk = ev["league_key"]
        if lk not in league_agg:
            league_agg[lk] = {
                "country_name": lk[1],
                "league_name": lk[2],
                "competition_id": lk[0],
                "total": 0,
                "finished": 0,
                "draws": 0,
                "internal_usable": 0,
                "market_usable": 0,
            }
        la = league_agg[lk]
        la["total"] += 1
        if ev["finished"]:
            la["finished"] += 1
        if ev["is_draw"]:
            la["draws"] += 1
        if ev["usable_internal"]:
            la["internal_usable"] += 1
        if ev["usable_market"]:
            la["market_usable"] += 1

        month = ev["month"]
        if month not in month_agg:
            month_agg[month] = {
                "month": month,
                "total": 0,
                "finished": 0,
                "draws": 0,
                "internal_usable": 0,
                "market_usable": 0,
            }
        ma = month_agg[month]
        ma["total"] += 1
        if ev["finished"]:
            ma["finished"] += 1
        if ev["is_draw"]:
            ma["draws"] += 1
        if ev["usable_internal"]:
            ma["internal_usable"] += 1
        if ev["usable_market"]:
            ma["market_usable"] += 1

    finished_count = counts["finished_fixtures"]
    draw_rate = _pct(counts["draw_results"], counts["finished_with_result"])

    def _pct_finished_for_reason(reason: str, count: int) -> float:
        if reason == "not_finished":
            return 0.0
        if finished_count <= 0:
            return 0.0
        return _pct(count, finished_count)

    exclusion_reasons = [
        {
            "reason": reason,
            "count": reason_counts[reason],
            "pct_total": _pct(reason_counts[reason], total),
            "pct_finished": _pct_finished_for_reason(reason, reason_counts[reason]),
        }
        for reason in _EXCLUSION_REASONS
    ]

    by_league = sorted(
        [
            {
                **la,
                "internal_coverage_pct": _pct(la["internal_usable"], la["total"]),
                "market_coverage_pct": _pct(la["market_usable"], la["total"]),
            }
            for la in league_agg.values()
        ],
        key=lambda x: (-x["internal_usable"], x["league_name"] or ""),
    )

    by_month = sorted(month_agg.values(), key=lambda x: x["month"])

    debug_samples = [sample for samples in debug_by_reason.values() for sample in samples]

    warnings: list[str] = []
    if total == 0:
        warnings.append("Nessuna fixture nel range selezionato.")
    elif counts["usable_internal_research"] == 0:
        warnings.append("Nessuna fixture utilizzabile per ricerca interna Credibilità X nel range.")

    return {
        "status": "ok",
        "version": VERSION,
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "only_eligible": only_eligible,
        },
        "summary": {
            "total_fixtures": total,
            "eligible_fixtures": eligible,
            **counts,
        },
        "coverage": {
            "cecchino": {
                "with_1x2_odds": counts["with_cecchino_1x2_odds"],
                "with_1x2_probabilities": counts["with_cecchino_1x2_probabilities"],
                "with_complete_1x2": counts["with_complete_cecchino_1x2"],
                "with_under_2_5": counts["with_cecchino_under_2_5"],
                "with_over_2_5": counts["with_cecchino_over_2_5"],
                "with_complete_goal_pair": counts["with_complete_cecchino_goal_pair"],
                "pct_complete_1x2": _pct(counts["with_complete_cecchino_1x2"], total),
                "pct_complete_goal_pair": _pct(counts["with_complete_cecchino_goal_pair"], total),
            },
            "book": {
                "with_1x2": counts["with_book_1x2"],
                "with_under_2_5": counts["with_book_under_2_5"],
                "with_over_2_5": counts["with_book_over_2_5"],
                "with_complete_goal_pair": counts["with_complete_book_goal_pair"],
                "with_complete_markets": counts["with_complete_book_markets"],
                "pct_complete_markets": _pct(counts["with_complete_book_markets"], total),
            },
            "research": {
                "usable_internal": counts["usable_internal_research"],
                "usable_market_comparison": counts["usable_market_comparison"],
                "pct_internal": _pct(counts["usable_internal_research"], total),
                "pct_internal_finished": _pct(counts["usable_internal_research"], finished_count),
                "pct_market": _pct(counts["usable_market_comparison"], total),
                "pct_market_finished": _pct(counts["usable_market_comparison"], finished_count),
            },
        },
        "target_distribution": {
            "draws": counts["draw_results"],
            "non_draws": counts["non_draw_results"],
            "draw_rate_pct": draw_rate,
        },
        "exclusion_reasons": exclusion_reasons,
        "by_league": by_league,
        "by_month": by_month,
        "debug_samples": debug_samples,
        "warnings": warnings,
    }
