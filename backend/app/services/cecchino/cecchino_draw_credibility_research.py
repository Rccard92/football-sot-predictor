"""Audit storico copertura dati Credibilità X — modulo ricerca offline (Fase 1A)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, MATCH_FINISHED, CecchinoTodayFixture
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    cecchino_final,
    cecchino_output,
    evaluate_internal_features,
    fixtures_in_range,
    pct,
    resolve_fulltime_score,
)

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


def _evaluate_fixture(row: CecchinoTodayFixture) -> dict[str, Any]:
    ev = evaluate_internal_features(row)
    final = ev["final"]
    output = ev["output"]

    finished = row.match_display_status == MATCH_FINISHED
    ft_home, ft_away = resolve_fulltime_score(row)
    has_result = finished and ft_home is not None and ft_away is not None
    is_draw = has_result and ft_home == ft_away

    has_complete_book_markets = ev["has_book_1x2"] and ev["has_book_goal_pair"]
    usable_internal = has_result and ev["has_internal_features"]
    usable_market = usable_internal and has_complete_book_markets

    primary_reason = _primary_exclusion_reason(
        finished=finished,
        has_result=has_result,
        output=output,
        final=final,
        has_invalid_numeric=ev["has_invalid_numeric"],
        has_cecchino_final=ev["has_cecchino_final"],
        has_1x2_odds=ev["has_1x2_odds"],
        has_1x2_prob=ev["has_1x2_prob"],
        has_under=ev["has_under"],
        has_over=ev["has_over"],
        has_book_1x2=ev["has_book_1x2"],
        has_book_under=ev["has_book_under"],
        has_book_over=ev["has_book_over"],
        usable_internal=usable_internal,
        usable_market=usable_market,
    )

    return {
        "finished": finished,
        "has_result": has_result,
        "is_draw": is_draw,
        "has_1x2_odds": ev["has_1x2_odds"],
        "has_1x2_prob": ev["has_1x2_prob"],
        "has_complete_1x2": ev["has_complete_1x2"],
        "has_under": ev["has_under"],
        "has_over": ev["has_over"],
        "has_complete_goal_pair": ev["has_complete_goal_pair"],
        "has_book_1x2": ev["has_book_1x2"],
        "has_book_under": ev["has_book_under"],
        "has_book_over": ev["has_book_over"],
        "has_complete_book_goal_pair": ev["has_book_goal_pair"],
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
    fixtures = fixtures_in_range(
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
    draw_rate = pct(counts["draw_results"], counts["finished_with_result"])

    def _pct_finished_for_reason(reason: str, count: int) -> float:
        if reason == "not_finished":
            return 0.0
        if finished_count <= 0:
            return 0.0
        return pct(count, finished_count)

    exclusion_reasons = [
        {
            "reason": reason,
            "count": reason_counts[reason],
            "pct_total": pct(reason_counts[reason], total),
            "pct_finished": _pct_finished_for_reason(reason, reason_counts[reason]),
        }
        for reason in _EXCLUSION_REASONS
    ]

    by_league = sorted(
        [
            {
                **la,
                "internal_coverage_pct": pct(la["internal_usable"], la["total"]),
                "market_coverage_pct": pct(la["market_usable"], la["total"]),
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
                "pct_complete_1x2": pct(counts["with_complete_cecchino_1x2"], total),
                "pct_complete_goal_pair": pct(counts["with_complete_cecchino_goal_pair"], total),
            },
            "book": {
                "with_1x2": counts["with_book_1x2"],
                "with_under_2_5": counts["with_book_under_2_5"],
                "with_over_2_5": counts["with_book_over_2_5"],
                "with_complete_goal_pair": counts["with_complete_book_goal_pair"],
                "with_complete_markets": counts["with_complete_book_markets"],
                "pct_complete_markets": pct(counts["with_complete_book_markets"], total),
            },
            "research": {
                "usable_internal": counts["usable_internal_research"],
                "usable_market_comparison": counts["usable_market_comparison"],
                "pct_internal": pct(counts["usable_internal_research"], total),
                "pct_internal_finished": pct(counts["usable_internal_research"], finished_count),
                "pct_market": pct(counts["usable_market_comparison"], total),
                "pct_market_finished": pct(counts["usable_market_comparison"], finished_count),
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
