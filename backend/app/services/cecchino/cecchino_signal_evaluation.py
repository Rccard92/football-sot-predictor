"""Valutazione esito segnali Cecchino dopo risultato partita."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    CecchinoSignalActivation,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture, MATCH_FINISHED
from app.services.cecchino.cecchino_signal_target_mapping import (
    apply_under_over_target_to_activation,
    remap_under_over_activations_in_range,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)


def _ft_available(match_result: dict[str, Any]) -> bool:
    ft = match_result.get("fulltime") or {}
    return ft.get("home") is not None and ft.get("away") is not None


def _ht_available(match_result: dict[str, Any]) -> bool:
    ht = match_result.get("halftime") or {}
    return ht.get("home") is not None and ht.get("away") is not None


def _evaluate_market(
    target_key: str,
    ft_home: int,
    ft_away: int,
    ht_home: int | None,
    ht_away: int | None,
) -> bool | None:
    if target_key == SEL_HOME:
        return ft_home > ft_away
    if target_key == SEL_DRAW:
        return ft_home == ft_away
    if target_key == SEL_AWAY:
        return ft_away > ft_home
    if target_key == SEL_ONE_X:
        return ft_home >= ft_away
    if target_key == SEL_X_TWO:
        return ft_away >= ft_home
    if target_key == SEL_ONE_TWO:
        return ft_home != ft_away

    if target_key in (SEL_UNDER_PT_1_5, SEL_OVER_PT_0_5, SEL_OVER_PT_1_5):
        if ht_home is None or ht_away is None:
            return None
        ht_total = ht_home + ht_away
        if target_key == SEL_UNDER_PT_1_5:
            return ht_total <= 1
        if target_key == SEL_OVER_PT_0_5:
            return ht_total >= 1
        return ht_total >= 2

    ft_total = ft_home + ft_away
    if target_key == SEL_UNDER_2_5:
        return ft_total <= 2
    if target_key == SEL_UNDER_3_5:
        return ft_total <= 3
    if target_key == SEL_OVER_1_5:
        return ft_total >= 2
    if target_key == SEL_OVER_2_5:
        return ft_total >= 3
    return None


def _build_evaluation_reason(
    target_key: str,
    ft_home: int,
    ft_away: int,
    won: bool,
) -> str | None:
    ft_total = ft_home + ft_away
    if target_key == SEL_UNDER_2_5:
        outcome = "vinto" if won else "perso"
        return f"Totale gol FT {ft_total}: Under 2.5 {outcome}"
    if target_key == SEL_OVER_2_5:
        outcome = "vinto" if won else "perso"
        return f"Totale gol FT {ft_total}: Over 2.5 {outcome}"
    return None


def evaluate_signal_activation(
    activation: CecchinoSignalActivation | dict[str, Any],
    match_result: dict[str, Any],
) -> dict[str, Any]:
    def _get(field: str) -> Any:
        if isinstance(activation, dict):
            return activation.get(field)
        return getattr(activation, field, None)

    target_key = _get("target_market_key")
    if not target_key:
        return {
            "evaluation_status": EVAL_NOT_EVALUABLE,
            "evaluation_reason": _get("evaluation_reason") or "missing_target_market_mapping",
            "evaluated_at": datetime.now(timezone.utc),
        }

    period = _get("target_period") or "FT"
    if not _ft_available(match_result) and period == "FT":
        return {
            "evaluation_status": EVAL_RESULT_MISSING,
            "evaluation_reason": "fulltime_result_missing",
            "evaluated_at": None,
        }
    if period == "HT" and not _ht_available(match_result):
        return {
            "evaluation_status": EVAL_RESULT_MISSING,
            "evaluation_reason": "halftime_result_missing",
            "evaluated_at": None,
        }

    ft = match_result.get("fulltime") or {}
    ht = match_result.get("halftime") or {}
    ft_home = int(ft.get("home"))
    ft_away = int(ft.get("away"))
    ht_home = int(ht["home"]) if ht.get("home") is not None else None
    ht_away = int(ht["away"]) if ht.get("away") is not None else None

    won = _evaluate_market(target_key, ft_home, ft_away, ht_home, ht_away)
    if won is None:
        return {
            "evaluation_status": EVAL_NOT_EVALUABLE,
            "evaluation_reason": "unsupported_target_market",
            "evaluated_at": datetime.now(timezone.utc),
        }

    status = EVAL_WON if won else EVAL_LOST
    return {
        "evaluation_status": status,
        "evaluation_reason": _build_evaluation_reason(target_key, ft_home, ft_away, won),
        "evaluated_at": datetime.now(timezone.utc),
        "ht_home_goals": ht_home,
        "ht_away_goals": ht_away,
        "ft_home_goals": ft_home,
        "ft_away_goals": ft_away,
    }


def match_result_from_fixture(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "halftime": {
            "home": row.score_halftime_home,
            "away": row.score_halftime_away,
            "available": row.score_halftime_home is not None and row.score_halftime_away is not None,
        },
        "fulltime": {
            "home": row.score_fulltime_home,
            "away": row.score_fulltime_away,
            "available": row.score_fulltime_home is not None and row.score_fulltime_away is not None,
        },
        "match_display_status": row.match_display_status,
        "fixture_status": row.fixture_status,
    }


def apply_evaluation_to_activation(
    activation: CecchinoSignalActivation,
    eval_result: dict[str, Any],
    *,
    result_status: str | None = None,
) -> None:
    activation.evaluation_status = eval_result["evaluation_status"]
    activation.evaluation_reason = eval_result.get("evaluation_reason")
    activation.evaluated_at = eval_result.get("evaluated_at")
    if eval_result.get("ht_home_goals") is not None:
        activation.ht_home_goals = eval_result["ht_home_goals"]
        activation.ht_away_goals = eval_result["ht_away_goals"]
        activation.ft_home_goals = eval_result["ft_home_goals"]
        activation.ft_away_goals = eval_result["ft_away_goals"]
    if result_status:
        activation.result_status = result_status


def evaluate_activations_for_fixture(db: Session, today_fixture_id: int) -> dict[str, int]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"evaluated": 0, "pending": 0, "not_evaluable": 0}

    match_result = match_result_from_fixture(row)
    result_status = row.match_display_status
    activations = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.today_fixture_id == int(today_fixture_id),
                CecchinoSignalActivation.is_current.is_(True),
            ),
        ).all(),
    )

    counts = {"evaluated": 0, "pending": 0, "not_evaluable": 0}
    for activation in activations:
        apply_under_over_target_to_activation(activation)
        eval_result = evaluate_signal_activation(activation, match_result)
        apply_evaluation_to_activation(activation, eval_result, result_status=result_status)
        if eval_result["evaluation_status"] in (EVAL_WON, EVAL_LOST):
            counts["evaluated"] += 1
        elif eval_result["evaluation_status"] == EVAL_RESULT_MISSING:
            counts["pending"] += 1
        elif eval_result["evaluation_status"] == EVAL_NOT_EVALUABLE:
            counts["not_evaluable"] += 1

    db.flush()
    return counts


def revaluate_signal_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    force: bool = False,
    sync_missing: bool = False,
    force_remap: bool = False,
    refresh_signal_odds: bool = False,
) -> dict[str, Any]:
    remapped = remap_under_over_activations_in_range(db, date_from=date_from, date_to=date_to)

    odds_refresh_summary: dict[str, int] | None = None
    if refresh_signal_odds:
        from app.services.cecchino.cecchino_signal_odds_refresh import refresh_activation_odds_from_kpi

        odds_refresh_summary = refresh_activation_odds_from_kpi(
            db,
            date_from=date_from,
            date_to=date_to,
            only_null=False,
            only_current=not force,
        )

    backfill_summary: dict[str, Any] | None = None
    if force_remap:
        from app.services.cecchino.cecchino_signal_backfill import backfill_signal_activations

        backfill_summary = backfill_signal_activations(
            db,
            date_from=date_from,
            date_to=date_to,
            only_missing=False,
            evaluate_after=True,
            force_remap=True,
        )
    elif sync_missing:
        from app.services.cecchino.cecchino_signal_backfill import (
            backfill_signal_activations,
            build_signal_diagnostics,
        )

        diag = build_signal_diagnostics(db, date_from=date_from, date_to=date_to)
        if (
            diag.get("fixtures_with_signal_matrix_count", 0) > 0
            and diag.get("current_signal_activations_count", 0) == 0
        ) or force:
            backfill_summary = backfill_signal_activations(
                db,
                date_from=date_from,
                date_to=date_to,
                only_missing=not force,
                evaluate_after=False,
            )

    query = select(CecchinoSignalActivation.today_fixture_id).where(
        CecchinoSignalActivation.scan_date >= date_from,
        CecchinoSignalActivation.scan_date <= date_to,
    )
    if not force:
        query = query.where(CecchinoSignalActivation.is_current.is_(True))

    fixture_ids = {
        int(fid)
        for fid in db.scalars(query.distinct()).all()
        if fid is not None
    }

    totals = {"fixtures": len(fixture_ids), "evaluated": 0, "pending": 0, "not_evaluable": 0}
    for fid in fixture_ids:
        counts = evaluate_activations_for_fixture(db, fid)
        totals["evaluated"] += counts["evaluated"]
        totals["pending"] += counts["pending"]
        totals["not_evaluable"] += counts["not_evaluable"]

    db.commit()
    totals["remapped"] = remapped
    totals["force_remap"] = force_remap
    if odds_refresh_summary is not None:
        totals["odds_refresh_summary"] = odds_refresh_summary
    if backfill_summary is not None:
        totals["backfill_summary"] = backfill_summary
    return totals
