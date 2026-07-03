"""Sync e valutazione Segnali KPI (righe Pannello KPI con rating >= 50)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_kpi_signal_activation import (
    DEFAULT_STAKE_UNITS,
    KPI_EVAL_LOST,
    KPI_EVAL_NOT_EVALUABLE,
    KPI_EVAL_PENDING,
    KPI_EVAL_RESULT_MISSING,
    KPI_EVAL_WON,
    CecchinoKpiSignalActivation,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_VERSION
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
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

MIN_KPI_RATING = 50

RATING_BUCKETS: tuple[str, ...] = ("50-59", "60-69", "70-79", "80-89", "90-99", "100")

KPI_MARKET_FOR_KEY: dict[str, str] = {
    SEL_HOME: MARKET_1X2,
    SEL_DRAW: MARKET_1X2,
    SEL_AWAY: MARKET_1X2,
    SEL_ONE_X: MARKET_DC,
    SEL_X_TWO: MARKET_DC,
    SEL_ONE_TWO: MARKET_DC,
    SEL_OVER_1_5: MARKET_OU,
    SEL_OVER_2_5: MARKET_OU,
    SEL_UNDER_2_5: MARKET_OU,
    SEL_UNDER_3_5: MARKET_OU,
    SEL_UNDER_PT_1_5: MARKET_OU_FH,
    SEL_OVER_PT_0_5: MARKET_OU_FH,
    SEL_OVER_PT_1_5: MARKET_OU_FH,
}

KPI_SELECTION_LABELS: dict[str, str] = {
    SEL_HOME: "1",
    SEL_DRAW: "X",
    SEL_AWAY: "2",
    SEL_ONE_X: "1X",
    SEL_X_TWO: "X2",
    SEL_ONE_TWO: "12",
    SEL_OVER_1_5: "Over 1.5",
    SEL_OVER_2_5: "Over 2.5",
    SEL_UNDER_2_5: "Under 2.5",
    SEL_UNDER_3_5: "Under 3.5",
    SEL_UNDER_PT_1_5: "Under PT 1.5",
    SEL_OVER_PT_0_5: "Over PT 0.5",
    SEL_OVER_PT_1_5: "Over PT 1.5",
}

_HEATMAP_SELECTION_ROWS: tuple[str, ...] = tuple(KPI_SELECTION_LABELS.values())
HEATMAP_SELECTION_ROWS = _HEATMAP_SELECTION_ROWS


def extract_kpi_rating_score(row: dict[str, Any]) -> int | None:
    raw = row.get("rating")
    if raw is None:
        for key in ("score", "value", "rating_score"):
            if row.get(key) is not None:
                raw = row.get(key)
                break
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        score = int(round(float(raw)))
    elif isinstance(raw, dict):
        nested = raw.get("score") or raw.get("value") or raw.get("rating")
        if nested is None:
            return None
        score = int(round(float(nested)))
    elif isinstance(raw, str):
        match = re.search(r"(\d+(?:\.\d+)?)", raw.strip())
        if not match:
            return None
        score = int(round(float(match.group(1))))
    else:
        return None
    if score > 100:
        score = 100
    return score


def rating_bucket(rating_score: int | None) -> str | None:
    if rating_score is None or rating_score < MIN_KPI_RATING:
        return None
    if rating_score >= 100:
        return "100"
    if rating_score >= 90:
        return "90-99"
    if rating_score >= 80:
        return "80-89"
    if rating_score >= 70:
        return "70-79"
    if rating_score >= 60:
        return "60-69"
    return "50-59"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_selection_key(row: dict[str, Any]) -> str | None:
    market_key = str(row.get("market_key") or "").strip().upper()
    if market_key in KPI_MARKET_FOR_KEY:
        return market_key
    segno = str(row.get("segno") or row.get("label") or "").strip()
    for key, label in KPI_SELECTION_LABELS.items():
        if segno == label:
            return key
    return None


def normalize_kpi_row(row: dict[str, Any]) -> dict[str, Any] | None:
    selection_key = _resolve_selection_key(row)
    if not selection_key:
        return None
    quota_book = _float_or_none(row.get("quota_book"))
    if quota_book is None or quota_book <= 0:
        return None
    rating_score = extract_kpi_rating_score(row)
    if rating_score is None or rating_score < MIN_KPI_RATING:
        return None
    bucket = rating_bucket(rating_score)
    if bucket is None:
        return None
    score_acquisto = _float_or_none(row.get("score_acquisto"))
    score_pct = round(score_acquisto * 100, 2) if score_acquisto is not None else None
    return {
        "kpi_row_key": str(row.get("market_key") or selection_key),
        "selection_key": selection_key,
        "selection_label": str(row.get("segno") or row.get("label") or KPI_SELECTION_LABELS[selection_key]),
        "normalized_market": KPI_MARKET_FOR_KEY[selection_key],
        "rating_score": rating_score,
        "rating_label": row.get("rating_label"),
        "rating_bucket": bucket,
        "quota_book": Decimal(str(round(quota_book, 4))),
        "quota_cecchino": (
            Decimal(str(round(q, 4))) if (q := _float_or_none(row.get("quota_cecchino"))) is not None else None
        ),
        "prob_book": (
            Decimal(str(round(p, 4))) if (p := _float_or_none(row.get("prob_book"))) is not None else None
        ),
        "prob_cecchino": (
            Decimal(str(round(p, 4))) if (p := _float_or_none(row.get("prob_cecchino"))) is not None else None
        ),
        "edge_pct": (
            Decimal(str(round(e, 2))) if (e := _float_or_none(row.get("edge_pct"))) is not None else None
        ),
        "score_pct": Decimal(str(score_pct)) if score_pct is not None else None,
    }


def extract_kpi_signal_candidates(today_fixture: CecchinoTodayFixture) -> list[dict[str, Any]]:
    panel = today_fixture.kpi_panel_json or {}
    rows = panel.get("rows") or []
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized = normalize_kpi_row(row)
        if normalized:
            candidates.append(normalized)
    return candidates


def compute_profit_units(evaluation_status: str, quota_book: Decimal | float | None) -> Decimal | None:
    if evaluation_status == KPI_EVAL_WON:
        if quota_book is None:
            return None
        return Decimal(str(round(float(quota_book) - 1.0, 4)))
    if evaluation_status == KPI_EVAL_LOST:
        return Decimal("-1")
    return None


def evaluate_kpi_signal_activation(
    db: Session,
    activation: CecchinoKpiSignalActivation,
    *,
    fixture: CecchinoTodayFixture | None = None,
) -> dict[str, Any]:
    from app.services.cecchino.cecchino_signal_evaluation import (
        evaluate_market_selection,
        match_result_from_fixture,
    )

    row = fixture or db.get(CecchinoTodayFixture, int(activation.today_fixture_id))
    if row is None:
        activation.evaluation_status = KPI_EVAL_NOT_EVALUABLE
        activation.evaluation_reason = "fixture_not_found"
        activation.profit_units = None
        activation.evaluated_at = datetime.now(timezone.utc)
        return {"evaluation_status": KPI_EVAL_NOT_EVALUABLE}

    match_result = match_result_from_fixture(row)
    eval_result = evaluate_market_selection(str(activation.selection_key), match_result)
    status = str(eval_result.get("evaluation_status") or KPI_EVAL_PENDING)
    if status == KPI_EVAL_RESULT_MISSING:
        status = KPI_EVAL_PENDING

    activation.evaluation_status = status
    activation.evaluation_reason = eval_result.get("evaluation_reason")
    activation.evaluated_at = eval_result.get("evaluated_at")
    activation.result_home_ft = eval_result.get("result_home_ft")
    activation.result_away_ft = eval_result.get("result_away_ft")
    activation.result_home_ht = eval_result.get("result_home_ht")
    activation.result_away_ht = eval_result.get("result_away_ht")
    activation.profit_units = compute_profit_units(status, activation.quota_book)
    db.flush()
    return {
        "evaluation_status": status,
        "profit_units": float(activation.profit_units) if activation.profit_units is not None else None,
    }


def _find_current_activation(
    db: Session,
    today_fixture_id: int,
    normalized_market: str,
    selection_key: str,
) -> CecchinoKpiSignalActivation | None:
    return db.scalar(
        select(CecchinoKpiSignalActivation).where(
            CecchinoKpiSignalActivation.today_fixture_id == int(today_fixture_id),
            CecchinoKpiSignalActivation.normalized_market == normalized_market,
            CecchinoKpiSignalActivation.selection_key == selection_key,
            CecchinoKpiSignalActivation.is_current.is_(True),
        ),
    )


def sync_kpi_signals_for_fixture(db: Session, today_fixture_id: int) -> dict[str, int]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"created": 0, "updated": 0, "deactivated": 0, "evaluated": 0}

    if row.eligibility_status != ELIGIBILITY_ELIGIBLE or not row.kpi_panel_json:
        return {"created": 0, "updated": 0, "deactivated": 0, "evaluated": 0}

    panel = row.kpi_panel_json or {}
    kpi_version = str(panel.get("version") or KPI_V2_VERSION)
    candidates = extract_kpi_signal_candidates(row)
    active_keys: set[tuple[str, str]] = set()
    created = updated = evaluated = 0

    for candidate in candidates:
        key = (candidate["normalized_market"], candidate["selection_key"])
        active_keys.add(key)
        existing = _find_current_activation(
            db,
            int(row.id),
            candidate["normalized_market"],
            candidate["selection_key"],
        )
        if existing is None:
            activation = CecchinoKpiSignalActivation(
                today_fixture_id=int(row.id),
                provider_fixture_id=int(row.provider_fixture_id),
                scan_date=row.scan_date,
                kickoff=row.kickoff,
                country_name=row.country_name,
                league_name=row.league_name,
                home_team_name=row.home_team_name,
                away_team_name=row.away_team_name,
                kpi_version=kpi_version,
                kpi_row_key=candidate["kpi_row_key"],
                selection_label=candidate["selection_label"],
                normalized_market=candidate["normalized_market"],
                selection_key=candidate["selection_key"],
                rating_score=candidate["rating_score"],
                rating_label=candidate.get("rating_label"),
                rating_bucket=candidate["rating_bucket"],
                quota_book=candidate["quota_book"],
                quota_cecchino=candidate.get("quota_cecchino"),
                prob_book=candidate.get("prob_book"),
                prob_cecchino=candidate.get("prob_cecchino"),
                edge_pct=candidate.get("edge_pct"),
                score_pct=candidate.get("score_pct"),
                stake_units=DEFAULT_STAKE_UNITS,
                is_current=True,
            )
            db.add(activation)
            db.flush()
            evaluate_kpi_signal_activation(db, activation, fixture=row)
            created += 1
            evaluated += 1
            continue

        changed = (
            existing.rating_score != candidate["rating_score"]
            or existing.quota_book != candidate["quota_book"]
            or existing.rating_bucket != candidate["rating_bucket"]
        )
        existing.kpi_version = kpi_version
        existing.kpi_row_key = candidate["kpi_row_key"]
        existing.selection_label = candidate["selection_label"]
        existing.rating_score = candidate["rating_score"]
        existing.rating_label = candidate.get("rating_label")
        existing.rating_bucket = candidate["rating_bucket"]
        existing.quota_book = candidate["quota_book"]
        existing.quota_cecchino = candidate.get("quota_cecchino")
        existing.prob_book = candidate.get("prob_book")
        existing.prob_cecchino = candidate.get("prob_cecchino")
        existing.edge_pct = candidate.get("edge_pct")
        existing.score_pct = candidate.get("score_pct")
        if changed:
            evaluate_kpi_signal_activation(db, existing, fixture=row)
            evaluated += 1
        updated += 1

    deactivated = 0
    current_rows = list(
        db.scalars(
            select(CecchinoKpiSignalActivation).where(
                CecchinoKpiSignalActivation.today_fixture_id == int(row.id),
                CecchinoKpiSignalActivation.is_current.is_(True),
            ),
        ).all(),
    )
    now = datetime.now(timezone.utc)
    for activation in current_rows:
        combo = (activation.normalized_market, activation.selection_key)
        if combo not in active_keys:
            activation.is_current = False
            activation.deactivated_at = now
            deactivated += 1

    db.flush()
    return {
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "evaluated": evaluated,
    }


def sync_kpi_signals_for_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    only_missing: bool = False,
    evaluate_after: bool = True,
) -> dict[str, Any]:
    fixtures = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
                CecchinoTodayFixture.kpi_panel_json.isnot(None),
            ),
        ).all(),
    )
    totals = {"fixtures": 0, "created": 0, "updated": 0, "deactivated": 0, "evaluated": 0, "skipped": 0}
    for fixture in fixtures:
        if only_missing:
            has_current = db.scalar(
                select(CecchinoKpiSignalActivation.id)
                .where(
                    CecchinoKpiSignalActivation.today_fixture_id == int(fixture.id),
                    CecchinoKpiSignalActivation.is_current.is_(True),
                )
                .limit(1),
            )
            if has_current is not None:
                totals["skipped"] += 1
                continue
        totals["fixtures"] += 1
        result = sync_kpi_signals_for_fixture(db, int(fixture.id))
        totals["created"] += result["created"]
        totals["updated"] += result["updated"]
        totals["deactivated"] += result["deactivated"]
        totals["evaluated"] += result["evaluated"]

    if evaluate_after:
        revaluate_kpi_signals_for_range(db, date_from=date_from, date_to=date_to)
    db.commit()
    totals["status"] = "ok"
    return totals


def backfill_kpi_signals(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    only_missing: bool = True,
    evaluate_after: bool = True,
) -> dict[str, Any]:
    return sync_kpi_signals_for_range(
        db,
        date_from=date_from,
        date_to=date_to,
        only_missing=only_missing,
        evaluate_after=evaluate_after,
    )


def revaluate_kpi_signals_for_fixture(db: Session, today_fixture_id: int) -> dict[str, int]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"evaluated": 0}
    activations = list(
        db.scalars(
            select(CecchinoKpiSignalActivation).where(
                CecchinoKpiSignalActivation.today_fixture_id == int(today_fixture_id),
                CecchinoKpiSignalActivation.is_current.is_(True),
            ),
        ).all(),
    )
    count = 0
    for activation in activations:
        evaluate_kpi_signal_activation(db, activation, fixture=row)
        count += 1
    db.flush()
    return {"evaluated": count}


def revaluate_kpi_signals_for_range(db: Session, *, date_from: date, date_to: date) -> dict[str, Any]:
    fixture_ids = list(
        db.scalars(
            select(CecchinoKpiSignalActivation.today_fixture_id)
            .where(
                CecchinoKpiSignalActivation.scan_date >= date_from,
                CecchinoKpiSignalActivation.scan_date <= date_to,
                CecchinoKpiSignalActivation.is_current.is_(True),
            )
            .distinct(),
        ).all(),
    )
    evaluated = 0
    for fid in fixture_ids:
        if fid is None:
            continue
        result = revaluate_kpi_signals_for_fixture(db, int(fid))
        evaluated += result["evaluated"]
    db.commit()
    return {"status": "ok", "fixtures": len(fixture_ids), "evaluated": evaluated}
