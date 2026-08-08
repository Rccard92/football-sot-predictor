"""BET-RESULTS-01 — Bet Builder Outcome Monitor (read-only).

Ricostruisce opportunity post-kickoff dagli snapshot CecchinoTodayFixture,
seleziona primary con Evidence Sort V2, valuta WON/LOST via evaluate_market_selection.

Nessun freeze, nessun backfill, nessuna API esterna, nessuna migration.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_PRIMARY_SELECTION_VERSION,
    BET_BUILDER_RESULTS_CONTRACT_VERSION,
    BET_BUILDER_RESULTS_START_DATE,
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
)
from app.services.cecchino.cecchino_bet_builder_markets import BET_BUILDER_MARKET_KEY_SET
from app.services.cecchino.cecchino_bet_builder_opportunity_aggregator import (
    _load_gi_payloads_batch,
    build_opportunities_for_rows,
)
from app.services.cecchino.cecchino_bet_builder_primary_selection import (
    sort_opportunities_by_evidence_strength,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_market_selection,
    match_result_from_fixture,
)

ROME_TZ = ZoneInfo("Europe/Rome")

OUTCOME_WON = EVAL_WON
OUTCOME_LOST = EVAL_LOST
OUTCOME_PENDING = EVAL_PENDING
OUTCOME_RESULT_MISSING = EVAL_RESULT_MISSING
OUTCOME_NOT_EVALUABLE = EVAL_NOT_EVALUABLE

VALID_OUTCOMES = frozenset(
    {
        OUTCOME_WON,
        OUTCOME_LOST,
        OUTCOME_PENDING,
        OUTCOME_RESULT_MISSING,
        OUTCOME_NOT_EVALUABLE,
    }
)

SORT_RECENT = "recent"
SORT_LOST_FIRST = "lost_first"
SORT_PURCHASABILITY_DESC = "purchasability_desc"
VALID_SORTS = frozenset({SORT_RECENT, SORT_LOST_FIRST, SORT_PURCHASABILITY_DESC})

MATCH_STATUS_CANONICAL = frozenset(
    {
        MATCH_UPCOMING,
        MATCH_LIVE,
        MATCH_FINISHED,
        MATCH_POSTPONED,
        MATCH_CANCELLED,
        "unknown",
    }
)


def clamp_results_date(value: date | None, *, today: date | None = None) -> date:
    """Normalizza una data al range [START, today Rome]."""
    today = today or datetime.now(ROME_TZ).date()
    start = BET_BUILDER_RESULTS_START_DATE
    if value is None:
        return today if today >= start else start
    if value < start:
        return start
    if value > today:
        return today
    return value


def normalize_match_status(row: CecchinoTodayFixture) -> str:
    status = str(row.match_display_status or "").strip().lower()
    if status in MATCH_STATUS_CANONICAL:
        return status
    if not status:
        return MATCH_UPCOMING
    return "unknown"


def evaluate_bet_builder_prediction_outcome(
    *,
    market_key: str,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Outcome prediction separato da match_status.

    cancelled/postponed → not_evaluable (mai LOST).
    upcoming / live senza score utile → pending.
    finished senza FT/HT → result_missing (via helper canonico).
    X PT può settlare su HT anche se LIVE.
    """
    match_status = normalize_match_status(row)

    if match_status in {MATCH_CANCELLED, MATCH_POSTPONED}:
        return {
            "prediction_outcome": OUTCOME_NOT_EVALUABLE,
            "evaluation_reason": f"match_{match_status}",
            "match_status": match_status,
        }

    match_result = match_result_from_fixture(row)
    ht = match_result.get("halftime") or {}
    ft = match_result.get("fulltime") or {}
    ht_ready = ht.get("home") is not None and ht.get("away") is not None
    ft_ready = ft.get("home") is not None and ft.get("away") is not None

    # X PT: HT disponibile → valuta anche in live
    from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT

    if market_key == SEL_DRAW_PT:
        if ht_ready:
            ev = evaluate_market_selection(market_key, match_result)
            return {
                "prediction_outcome": ev.get("evaluation_status") or OUTCOME_NOT_EVALUABLE,
                "evaluation_reason": ev.get("evaluation_reason"),
                "match_status": match_status,
                "result_home_ht": ev.get("result_home_ht"),
                "result_away_ht": ev.get("result_away_ht"),
                "result_home_ft": row.score_fulltime_home,
                "result_away_ft": row.score_fulltime_away,
            }
        if match_status == MATCH_FINISHED:
            return {
                "prediction_outcome": OUTCOME_RESULT_MISSING,
                "evaluation_reason": "halftime_result_missing",
                "match_status": match_status,
            }
        return {
            "prediction_outcome": OUTCOME_PENDING,
            "evaluation_reason": "awaiting_halftime_result",
            "match_status": match_status,
        }

    # Mercati FT
    if ft_ready:
        ev = evaluate_market_selection(market_key, match_result)
        return {
            "prediction_outcome": ev.get("evaluation_status") or OUTCOME_NOT_EVALUABLE,
            "evaluation_reason": ev.get("evaluation_reason"),
            "match_status": match_status,
            "result_home_ft": ev.get("result_home_ft"),
            "result_away_ft": ev.get("result_away_ft"),
            "result_home_ht": ev.get("result_home_ht"),
            "result_away_ht": ev.get("result_away_ht"),
        }

    if match_status == MATCH_FINISHED:
        return {
            "prediction_outcome": OUTCOME_RESULT_MISSING,
            "evaluation_reason": "fulltime_result_missing",
            "match_status": match_status,
        }

    return {
        "prediction_outcome": OUTCOME_PENDING,
        "evaluation_reason": "awaiting_fulltime_result",
        "match_status": match_status,
        "result_home_ft": row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home,
        "result_away_ft": row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away,
        "result_home_ht": row.score_halftime_home,
        "result_away_ht": row.score_halftime_away,
    }


def _enrich_opportunity_with_outcome(
    opp: dict[str, Any],
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    market_key = str((opp.get("market") or {}).get("market_key") or "")
    evaluation = evaluate_bet_builder_prediction_outcome(market_key=market_key, row=row)
    enriched = dict(opp)
    enriched["prediction_outcome"] = evaluation["prediction_outcome"]
    enriched["evaluation_reason"] = evaluation.get("evaluation_reason")
    enriched["match_status"] = evaluation["match_status"]
    return enriched


def _score_payload(row: CecchinoTodayFixture) -> dict[str, Any]:
    ft_home = row.score_fulltime_home
    ft_away = row.score_fulltime_away
    if ft_home is None and ft_away is None:
        ft_home = row.goals_home
        ft_away = row.goals_away
    return {
        "goals_home": row.goals_home,
        "goals_away": row.goals_away,
        "fulltime_home": ft_home,
        "fulltime_away": ft_away,
        "halftime_home": row.score_halftime_home,
        "halftime_away": row.score_halftime_away,
    }


def _fixture_results_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": row.provider_fixture_id,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "country": row.country_name,
        "league": row.league_name,
        "home": {
            "name": row.home_team_name,
            "logo": row.home_team_logo_url,
        },
        "away": {
            "name": row.away_team_name,
            "logo": row.away_team_logo_url,
        },
        "match_status": normalize_match_status(row),
        "elapsed_minutes": row.elapsed_minutes,
        "score": _score_payload(row),
    }


def _primary_passes_filters(
    primary: dict[str, Any],
    *,
    outcome: str | None,
    market_key: str | None,
    origin: str | None,
    min_purchasability: float | None,
) -> bool:
    if outcome and primary.get("prediction_outcome") != outcome:
        return False
    if market_key:
        mk = (primary.get("market") or {}).get("market_key")
        if mk != market_key:
            return False
    if origin and primary.get("origin") != origin:
        return False
    if min_purchasability is not None:
        score = (primary.get("purchasability_v31") or {}).get("score")
        if score is None:
            return False
        try:
            if float(score) < float(min_purchasability):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _sort_fixture_results(
    fixtures: list[dict[str, Any]],
    sort: str,
) -> list[dict[str, Any]]:
    copy = list(fixtures)

    def kickoff_key(item: dict[str, Any]) -> str:
        return str((item.get("fixture") or {}).get("kickoff") or "")

    if sort == SORT_LOST_FIRST:

        def lost_key(item: dict[str, Any]) -> tuple:
            outcome = (item.get("primary") or {}).get("prediction_outcome")
            is_lost = 0 if outcome == OUTCOME_LOST else 1
            return (is_lost, kickoff_key(item))

        copy.sort(key=lost_key, reverse=False)
        # Within same lost flag, more recent first → reverse kickoff within groups
        copy.sort(
            key=lambda item: (
                0 if (item.get("primary") or {}).get("prediction_outcome") == OUTCOME_LOST else 1,
                kickoff_key(item),
            ),
            reverse=False,
        )
        # Stable: first by lost, then by kickoff DESC
        copy.sort(key=kickoff_key, reverse=True)
        copy.sort(
            key=lambda item: 0
            if (item.get("primary") or {}).get("prediction_outcome") == OUTCOME_LOST
            else 1
        )
        return copy

    if sort == SORT_PURCHASABILITY_DESC:

        def purch_key(item: dict[str, Any]) -> tuple:
            score = (item.get("primary") or {}).get("purchasability_v31") or {}
            val = score.get("score")
            null = val is None
            try:
                num = -float(val) if val is not None else 0.0
            except (TypeError, ValueError):
                null = True
                num = 0.0
            return (1 if null else 0, num, kickoff_key(item))

        copy.sort(key=purch_key)
        return copy

    # Default: più recenti prima
    copy.sort(key=kickoff_key, reverse=True)
    return copy


def _build_summary(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """KPI solo sulle primary."""
    primary_predictions = len(fixtures)
    won = lost = pending = not_evaluable = result_missing = 0
    live_or_pending = 0

    for item in fixtures:
        primary = item.get("primary") or {}
        outcome = primary.get("prediction_outcome")
        match_status = (item.get("fixture") or {}).get("match_status")
        if outcome == OUTCOME_WON:
            won += 1
        elif outcome == OUTCOME_LOST:
            lost += 1
        elif outcome == OUTCOME_PENDING:
            pending += 1
        elif outcome == OUTCOME_NOT_EVALUABLE:
            not_evaluable += 1
        elif outcome == OUTCOME_RESULT_MISSING:
            result_missing += 1

        if match_status == MATCH_LIVE or outcome == OUTCOME_PENDING:
            live_or_pending += 1

    settled = won + lost
    win_rate = round(won / settled, 4) if settled > 0 else None

    return {
        "primary_predictions": primary_predictions,
        "settled": settled,
        "won": won,
        "lost": lost,
        "pending": pending,
        "not_evaluable": not_evaluable,
        "result_missing": result_missing,
        "live_or_pending": live_or_pending,
        "win_rate": win_rate,
    }


def aggregate_bet_builder_results(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    outcome: str | None = None,
    market_key: str | None = None,
    origin: str | None = None,
    min_purchasability: float | None = None,
    sort: str = SORT_RECENT,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read-model Results — solo dati persistiti, nessuna API esterna."""
    today = datetime.now(ROME_TZ).date()
    start = BET_BUILDER_RESULTS_START_DATE

    d_from = clamp_results_date(date_from, today=today)
    d_to = clamp_results_date(date_to, today=today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    # Mai interrogare prima di START
    if d_from < start:
        d_from = start
    if d_to < start:
        d_to = start

    outcome_filter = str(outcome).strip().lower() if outcome else None
    if outcome_filter and outcome_filter not in VALID_OUTCOMES:
        outcome_filter = None

    market_filter = str(market_key).strip().upper() if market_key else None
    if market_filter and market_filter not in BET_BUILDER_MARKET_KEY_SET:
        market_filter = None

    origin_filter = str(origin).strip().lower() if origin else None
    if origin_filter not in {
        ORIGIN_PRICE,
        ORIGIN_SIGNALS,
        ORIGIN_PRICE_AND_SIGNALS,
        None,
    }:
        origin_filter = None

    sort_key = str(sort or SORT_RECENT).strip().lower()
    if sort_key not in VALID_SORTS:
        sort_key = SORT_RECENT

    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    rows = list(
        db.scalars(
            select(CecchinoTodayFixture)
            .where(
                CecchinoTodayFixture.scan_date >= d_from,
                CecchinoTodayFixture.scan_date <= d_to,
                CecchinoTodayFixture.scan_date >= start,
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            )
            .order_by(CecchinoTodayFixture.kickoff.desc().nullslast())
        ).all()
    )

    gi_by_fixture, _max_gi = _load_gi_payloads_batch(db, rows)
    # Costruisci TUTTE le opportunity (senza filtro market/origin a livello build
    # se filtriamo sulla primary — ma se market/origin filter sono impostati
    # applicarli dopo sulla primary. Build completo per ranking corretto.
    all_opps, _max_v31 = build_opportunities_for_rows(
        rows,
        gi_by_fixture=gi_by_fixture,
        market_filter=None,
        origin_filter=None,
        freshness_scan_date=None,
    )

    by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)
    row_by_id: dict[int, CecchinoTodayFixture] = {int(r.id): r for r in rows}
    for opp in all_opps:
        fid = int((opp.get("fixture") or {}).get("today_fixture_id") or 0)
        if fid:
            by_fixture[fid].append(opp)

    fixture_results: list[dict[str, Any]] = []
    for fid, opps in by_fixture.items():
        row = row_by_id.get(fid)
        if row is None:
            continue
        enriched = [_enrich_opportunity_with_outcome(o, row) for o in opps]
        ranked = sort_opportunities_by_evidence_strength(enriched)
        primary = ranked[0] if ranked else None
        if primary is None:
            continue
        if not _primary_passes_filters(
            primary,
            outcome=outcome_filter,
            market_key=market_filter,
            origin=origin_filter,
            min_purchasability=min_purchasability,
        ):
            continue
        others = ranked[1:]
        fixture_results.append(
            {
                "fixture": _fixture_results_block(row),
                "primary": primary,
                "other_opportunities": others,
                "primary_selection_version": BET_BUILDER_PRIMARY_SELECTION_VERSION,
            }
        )

    fixture_results = _sort_fixture_results(fixture_results, sort_key)
    total = len(fixture_results)
    page = fixture_results[offset : offset + limit]
    summary = _build_summary(fixture_results)

    return {
        "contract_version": BET_BUILDER_RESULTS_CONTRACT_VERSION,
        "available_from": start.isoformat(),
        "primary_selection_version": BET_BUILDER_PRIMARY_SELECTION_VERSION,
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "timezone": "Europe/Rome",
        "sort": sort_key,
        "limit": limit,
        "offset": offset,
        "total": total,
        "summary": summary,
        "fixtures": page,
    }
