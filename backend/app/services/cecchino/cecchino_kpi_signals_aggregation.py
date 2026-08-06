"""Aggregazioni statistiche Segnali KPI."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_kpi_signal_activation import (
    KPI_EVAL_LOST,
    KPI_EVAL_NOT_EVALUABLE,
    KPI_EVAL_PENDING,
    KPI_EVAL_RESULT_MISSING,
    KPI_EVAL_WON,
    CecchinoKpiSignalActivation,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_kpi_signals import (
    HEATMAP_SELECTION_ROWS,
    KPI_MARKET_FOR_KEY,
    KPI_SIGNAL_MARKET_DEFS,
    KPI_SIGNAL_MARKET_OPTIONS,
    MIN_KPI_RATING,
    RATING_BUCKETS,
    extract_kpi_rating_score,
    normalize_kpi_row,
)
from app.services.cecchino.cecchino_kpi_signals_purchasability import (
    PURCHASABILITY_CLASS_KEYS,
    PURCHASABILITY_FILTER_STATUSES,
    PURCHASABILITY_QUALITY_VALUES,
    PURCHASABILITY_STATUS_SCORE,
    PURCHASABILITY_STATUS_SCORE_PROVISIONAL,
    PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE,
    PURCHASABILITY_STATUS_UNSUPPORTED,
    PURCHASABILITY_VERSIONS,
    purchasability_filter_options,
    serialize_purchasability_from_activation,
)
from app.services.cecchino.cecchino_purchasability_v3_opposition import SUPPORTED_V3_MARKETS


def _float_odds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _win_rate(won: int, lost: int) -> float | None:
    settled = won + lost
    if settled <= 0:
        return None
    return round((won / settled) * 100.0, 1)


def _profit_metrics(rows: list[CecchinoKpiSignalActivation]) -> dict[str, Any]:
    won = lost = pending = 0
    profit_total = 0.0
    sum_all_odds = 0.0
    sum_won_odds = 0.0
    all_with_odds = 0
    won_with_odds = 0

    for row in rows:
        status = row.evaluation_status
        if status == KPI_EVAL_WON:
            won += 1
            odds = _float_odds(row.quota_book)
            if odds is not None:
                all_with_odds += 1
                won_with_odds += 1
                sum_all_odds += odds
                sum_won_odds += odds
            profit = _float_odds(row.profit_units)
            if profit is not None:
                profit_total += profit
        elif status == KPI_EVAL_LOST:
            lost += 1
            odds = _float_odds(row.quota_book)
            if odds is not None:
                all_with_odds += 1
                sum_all_odds += odds
            profit = _float_odds(row.profit_units)
            if profit is not None:
                profit_total += profit
        elif status in (KPI_EVAL_PENDING, KPI_EVAL_RESULT_MISSING):
            pending += 1

    settled = won + lost
    avg_book_odds_all = round(sum_all_odds / all_with_odds, 2) if all_with_odds > 0 else None
    avg_book_odds_won = round(sum_won_odds / won_with_odds, 2) if won_with_odds > 0 else None
    win_rate = _win_rate(won, lost)
    win_rate_decimal = (won / settled) if settled > 0 else None
    quota_void = round(1.0 / win_rate_decimal, 2) if win_rate_decimal and win_rate_decimal > 0 else None
    roi_pct = round((profit_total / settled) * 100.0, 2) if settled > 0 else None

    return {
        "activations": len(rows),
        "settled": settled,
        "won": won,
        "lost": lost,
        "pending": pending,
        "not_evaluable": sum(1 for r in rows if r.evaluation_status == KPI_EVAL_NOT_EVALUABLE),
        "win_rate": win_rate,
        "avg_book_odds_all": avg_book_odds_all,
        "avg_book_odds_won": avg_book_odds_won,
        "quota_void": quota_void,
        "profit_units": round(profit_total, 2) if settled > 0 else round(profit_total, 2),
        "roi_pct": roi_pct,
    }


def validate_purchasability_filters(
    *,
    purchasability_version: str | None = None,
    purchasability_status: str | None = None,
    purchasability_class: str | None = None,
    purchasability_score_min: float | None = None,
    purchasability_score_max: float | None = None,
    purchasability_quality: str | None = None,
) -> None:
    """Valida filtri Acquistabilità. Senza version non applicare sottofiltri."""
    has_child = any(
        v is not None and v != ""
        for v in (
            purchasability_status,
            purchasability_class,
            purchasability_score_min,
            purchasability_score_max,
            purchasability_quality,
        )
    )
    if has_child and not purchasability_version:
        raise HTTPException(
            status_code=422,
            detail="purchasability_version is required when other purchasability filters are set",
        )
    if not purchasability_version:
        return
    if purchasability_version not in PURCHASABILITY_VERSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"purchasability_version must be one of: {', '.join(PURCHASABILITY_VERSIONS)}",
        )
    if purchasability_status and purchasability_status not in PURCHASABILITY_FILTER_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"purchasability_status must be one of: {', '.join(PURCHASABILITY_FILTER_STATUSES)}",
        )
    if purchasability_class and purchasability_class not in PURCHASABILITY_CLASS_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"purchasability_class must be one of: {', '.join(PURCHASABILITY_CLASS_KEYS)}",
        )
    if purchasability_quality and purchasability_quality not in PURCHASABILITY_QUALITY_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"purchasability_quality must be one of: {', '.join(PURCHASABILITY_QUALITY_VALUES)}",
        )
    for label, value in (
        ("purchasability_score_min", purchasability_score_min),
        ("purchasability_score_max", purchasability_score_max),
    ):
        if value is None:
            continue
        if value < 0 or value > 100:
            raise HTTPException(status_code=422, detail=f"{label} must be between 0 and 100")
    if (
        purchasability_score_min is not None
        and purchasability_score_max is not None
        and purchasability_score_min > purchasability_score_max
    ):
        raise HTTPException(status_code=422, detail="purchasability_score_min cannot exceed purchasability_score_max")


def _apply_purchasability_filters(
    query,
    *,
    purchasability_version: str | None = None,
    purchasability_status: str | None = None,
    purchasability_class: str | None = None,
    purchasability_score_min: float | None = None,
    purchasability_score_max: float | None = None,
    purchasability_quality: str | None = None,
):
    if not purchasability_version:
        return query

    if purchasability_version == "v3":
        status_col = CecchinoKpiSignalActivation.purchasability_v3_status
        score_col = CecchinoKpiSignalActivation.purchasability_v3_score
        class_col = CecchinoKpiSignalActivation.purchasability_v3_class_key
        quality_col = CecchinoKpiSignalActivation.purchasability_v3_calculation_quality
    else:
        status_col = CecchinoKpiSignalActivation.purchasability_v31_status
        score_col = CecchinoKpiSignalActivation.purchasability_v31_score
        class_col = CecchinoKpiSignalActivation.purchasability_v31_class_key
        quality_col = CecchinoKpiSignalActivation.purchasability_v31_calculation_quality

    if purchasability_status:
        if purchasability_status == PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE:
            query = query.where(
                (status_col.is_(None)) | (status_col == PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE)
            )
        else:
            query = query.where(status_col == purchasability_status)
    if purchasability_class:
        query = query.where(class_col == purchasability_class)
    if purchasability_quality:
        query = query.where(quality_col == purchasability_quality)
    if purchasability_score_min is not None:
        query = query.where(score_col.is_not(None), score_col >= purchasability_score_min)
    if purchasability_score_max is not None:
        query = query.where(score_col.is_not(None), score_col <= purchasability_score_max)
    return query


def _base_query(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None = None,
    selection_key: str | None = None,
    normalized_market: str | None = None,
    evaluation_status: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    only_current: bool = True,
    purchasability_version: str | None = None,
    purchasability_status: str | None = None,
    purchasability_class: str | None = None,
    purchasability_score_min: float | None = None,
    purchasability_score_max: float | None = None,
    purchasability_quality: str | None = None,
):
    query = select(CecchinoKpiSignalActivation).where(
        CecchinoKpiSignalActivation.scan_date >= date_from,
        CecchinoKpiSignalActivation.scan_date <= date_to,
    )
    if only_current:
        query = query.where(CecchinoKpiSignalActivation.is_current.is_(True))
    if rating_bucket:
        query = query.where(CecchinoKpiSignalActivation.rating_bucket == rating_bucket)
    if selection_key:
        query = query.where(CecchinoKpiSignalActivation.selection_key == selection_key)
    if normalized_market:
        query = query.where(CecchinoKpiSignalActivation.normalized_market == normalized_market)
    if evaluation_status:
        query = query.where(CecchinoKpiSignalActivation.evaluation_status == evaluation_status)
    if league_name:
        query = query.where(CecchinoKpiSignalActivation.league_name == league_name)
    if country_name:
        query = query.where(CecchinoKpiSignalActivation.country_name == country_name)
    return _apply_purchasability_filters(
        query,
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
    )


def _count_filters_kwargs(
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None,
    selection_key: str | None,
    normalized_market: str | None,
    evaluation_status: str | None,
    league_name: str | None,
    country_name: str | None,
    only_current: bool,
    purchasability_version: str | None,
    purchasability_status: str | None,
    purchasability_class: str | None,
    purchasability_score_min: float | None,
    purchasability_score_max: float | None,
    purchasability_quality: str | None,
):
    clauses = [
        CecchinoKpiSignalActivation.scan_date >= date_from,
        CecchinoKpiSignalActivation.scan_date <= date_to,
    ]
    if only_current:
        clauses.append(CecchinoKpiSignalActivation.is_current.is_(True))
    if rating_bucket:
        clauses.append(CecchinoKpiSignalActivation.rating_bucket == rating_bucket)
    if selection_key:
        clauses.append(CecchinoKpiSignalActivation.selection_key == selection_key)
    if normalized_market:
        clauses.append(CecchinoKpiSignalActivation.normalized_market == normalized_market)
    if evaluation_status:
        clauses.append(CecchinoKpiSignalActivation.evaluation_status == evaluation_status)
    if league_name:
        clauses.append(CecchinoKpiSignalActivation.league_name == league_name)
    if country_name:
        clauses.append(CecchinoKpiSignalActivation.country_name == country_name)

    query = select(func.count()).select_from(CecchinoKpiSignalActivation).where(*clauses)
    query = _apply_purchasability_filters(
        query,
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
    )
    return query


def _build_diagnostics(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    fixtures = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            ),
        ).all(),
    )
    kpi_rows_seen = 0
    kpi_rows_supported = 0
    kpi_rows_unsupported = 0
    below_50 = 0
    without_book = 0
    fixtures_with_kpi = 0
    for fixture in fixtures:
        panel = fixture.kpi_panel_json or {}
        rows = panel.get("rows") or []
        if not rows:
            continue
        fixtures_with_kpi += 1
        for row in rows:
            if not isinstance(row, dict):
                continue
            kpi_rows_seen += 1
            score = extract_kpi_rating_score(row)
            if score is None or score < MIN_KPI_RATING:
                below_50 += 1
            if _float_odds(row.get("quota_book")) is None:
                without_book += 1
            normalized = normalize_kpi_row(row)
            if normalized:
                kpi_rows_supported += 1
            else:
                market_key = str(row.get("market_key") or "").strip().upper()
                if market_key and market_key not in KPI_MARKET_FOR_KEY:
                    kpi_rows_unsupported += 1

    activations = list(
        db.scalars(
            select(CecchinoKpiSignalActivation).where(
                CecchinoKpiSignalActivation.scan_date >= date_from,
                CecchinoKpiSignalActivation.scan_date <= date_to,
                CecchinoKpiSignalActivation.is_current.is_(True),
            ),
        ).all(),
    )
    created = len(activations)
    by_market: dict[str, int] = {d["selection_key"]: 0 for d in KPI_SIGNAL_MARKET_DEFS}
    rows_with_v3 = rows_without_v3 = 0
    rows_with_v31 = rows_without_v31 = 0
    v31_provisional = v31_definitive = 0
    v3_unsupported = 0
    for act in activations:
        by_market[act.selection_key] = by_market.get(act.selection_key, 0) + 1
        v3_status = act.purchasability_v3_status
        if v3_status and v3_status != PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE:
            rows_with_v3 += 1
        else:
            rows_without_v3 += 1
        if v3_status == PURCHASABILITY_STATUS_UNSUPPORTED:
            v3_unsupported += 1
        v31_status = act.purchasability_v31_status
        if v31_status and v31_status != PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE:
            rows_with_v31 += 1
        else:
            rows_without_v31 += 1
        if v31_status == PURCHASABILITY_STATUS_SCORE_PROVISIONAL:
            v31_provisional += 1
        elif v31_status == PURCHASABILITY_STATUS_SCORE:
            v31_definitive += 1

    return {
        "today_fixtures_count": len(fixtures),
        "fixtures_with_kpi_panel": fixtures_with_kpi,
        "kpi_rows_seen": kpi_rows_seen,
        "kpi_rows_supported": kpi_rows_supported,
        "kpi_rows_unsupported": kpi_rows_unsupported,
        "kpi_signals_created": created,
        "kpi_rows_below_50": below_50,
        "kpi_rows_without_book_odds": without_book,
        "supported_market_definitions": len(KPI_SIGNAL_MARKET_DEFS),
        "activations_created_by_market": by_market,
        "rows_with_v3_snapshot": rows_with_v3,
        "rows_without_v3_snapshot": rows_without_v3,
        "rows_with_v31_snapshot": rows_with_v31,
        "rows_without_v31_snapshot": rows_without_v31,
        "v31_provisional_count": v31_provisional,
        "v31_definitive_count": v31_definitive,
        "v3_unsupported_count": v3_unsupported,
        "purchasability_snapshot_extraction_errors": 0,
        "v3_supported_markets": sorted(SUPPORTED_V3_MARKETS),
    }


def _filter_payload(
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None,
    selection_key: str | None,
    normalized_market: str | None,
    evaluation_status: str | None,
    league_name: str | None,
    country_name: str | None,
    only_current: bool,
    purchasability_version: str | None,
    purchasability_status: str | None,
    purchasability_class: str | None,
    purchasability_score_min: float | None,
    purchasability_score_max: float | None,
    purchasability_quality: str | None,
) -> dict[str, Any]:
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "rating_bucket": rating_bucket,
        "selection_key": selection_key,
        "normalized_market": normalized_market,
        "evaluation_status": evaluation_status,
        "league_name": league_name,
        "country_name": country_name,
        "only_current": only_current,
        "purchasability_version": purchasability_version,
        "purchasability_status": purchasability_status,
        "purchasability_class": purchasability_class,
        "purchasability_score_min": purchasability_score_min,
        "purchasability_score_max": purchasability_score_max,
        "purchasability_quality": purchasability_quality,
    }


def build_kpi_signals_summary(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None = None,
    selection_key: str | None = None,
    normalized_market: str | None = None,
    evaluation_status: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    only_current: bool = True,
    include_diagnostics: bool = True,
    purchasability_version: str | None = None,
    purchasability_status: str | None = None,
    purchasability_class: str | None = None,
    purchasability_score_min: float | None = None,
    purchasability_score_max: float | None = None,
    purchasability_quality: str | None = None,
) -> dict[str, Any]:
    validate_purchasability_filters(
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
    )
    filters = _filter_payload(
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
    )
    rows = list(
        db.scalars(
            _base_query(
                db,
                date_from=date_from,
                date_to=date_to,
                rating_bucket=rating_bucket,
                selection_key=selection_key,
                normalized_market=normalized_market,
                evaluation_status=evaluation_status,
                league_name=league_name,
                country_name=country_name,
                only_current=only_current,
                purchasability_version=purchasability_version,
                purchasability_status=purchasability_status,
                purchasability_class=purchasability_class,
                purchasability_score_min=purchasability_score_min,
                purchasability_score_max=purchasability_score_max,
                purchasability_quality=purchasability_quality,
            ),
        ).all(),
    )
    overall = _profit_metrics(rows)

    by_bucket_map: dict[str, list[CecchinoKpiSignalActivation]] = {b: [] for b in RATING_BUCKETS}
    by_selection_map: dict[str, list[CecchinoKpiSignalActivation]] = {}
    for row in rows:
        by_bucket_map.setdefault(row.rating_bucket, []).append(row)
        by_selection_map.setdefault(row.selection_label, []).append(row)

    by_rating_bucket = [
        {"rating_bucket": bucket, **_profit_metrics(by_bucket_map.get(bucket, []))}
        for bucket in RATING_BUCKETS
        if by_bucket_map.get(bucket)
    ]
    by_selection = [
        {"selection_label": label, **_profit_metrics(group_rows)}
        for label, group_rows in sorted(by_selection_map.items(), key=lambda x: x[0])
    ]

    heatmap_cells: list[dict[str, Any]] = []
    for selection_label in HEATMAP_SELECTION_ROWS:
        for bucket in RATING_BUCKETS:
            cell_rows = [
                r
                for r in rows
                if r.selection_label == selection_label and r.rating_bucket == bucket
            ]
            if not cell_rows:
                continue
            metrics = _profit_metrics(cell_rows)
            heatmap_cells.append(
                {
                    "selection_label": selection_label,
                    "rating_bucket": bucket,
                    **metrics,
                },
            )

    ranked = [
        {
            "selection_label": r.selection_label,
            "rating_bucket": r.rating_bucket,
            "scan_date": r.scan_date.isoformat(),
            "match": f"{r.home_team_name} vs {r.away_team_name}",
            "profit_units": _float_odds(r.profit_units),
            "roi_pct": None,
            "evaluation_status": r.evaluation_status,
        }
        for r in rows
        if r.evaluation_status in (KPI_EVAL_WON, KPI_EVAL_LOST) and r.profit_units is not None
    ]
    best_profit = sorted(ranked, key=lambda x: float(x["profit_units"] or 0), reverse=True)[:10]
    worst_profit = sorted(ranked, key=lambda x: float(x["profit_units"] or 0))[:10]

    bucket_roi = [
        {**item, "roi_pct": item.get("roi_pct")}
        for item in by_rating_bucket
        if item.get("roi_pct") is not None
    ]
    best_roi = sorted(bucket_roi, key=lambda x: float(x.get("roi_pct") or 0), reverse=True)[:5]

    payload: dict[str, Any] = {
        "status": "ok",
        "filters": filters,
        "purchasability_filter_options": purchasability_filter_options(),
        "market_options": list(KPI_SIGNAL_MARKET_OPTIONS),
        "overall": overall,
        "by_rating_bucket": by_rating_bucket,
        "by_selection": by_selection,
        "heatmap": {
            "rows": list(HEATMAP_SELECTION_ROWS),
            "columns": list(RATING_BUCKETS),
            "cells": heatmap_cells,
        },
        "top": {
            "best_profit": best_profit,
            "best_roi": best_roi,
            "worst_profit": worst_profit,
        },
    }
    if include_diagnostics:
        payload["diagnostics"] = _build_diagnostics(db, date_from=date_from, date_to=date_to)
    return payload


def serialize_kpi_activation(row: CecchinoKpiSignalActivation) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "today_fixture_id": int(row.today_fixture_id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "scan_date": row.scan_date.isoformat(),
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "country_name": row.country_name,
        "league_name": row.league_name,
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "kpi_version": row.kpi_version,
        "kpi_row_key": row.kpi_row_key,
        "selection_label": row.selection_label,
        "normalized_market": row.normalized_market,
        "selection_key": row.selection_key,
        "rating_score": row.rating_score,
        "rating_label": row.rating_label,
        "rating_bucket": row.rating_bucket,
        "quota_book": _float_odds(row.quota_book),
        "quota_cecchino": _float_odds(row.quota_cecchino),
        "prob_book": _float_odds(row.prob_book),
        "prob_cecchino": _float_odds(row.prob_cecchino),
        "edge_pct": _float_odds(row.edge_pct),
        "score_pct": _float_odds(row.score_pct),
        "evaluation_status": row.evaluation_status,
        "evaluation_reason": row.evaluation_reason,
        "result_home_ft": row.result_home_ft,
        "result_away_ft": row.result_away_ft,
        "result_home_ht": row.result_home_ht,
        "result_away_ht": row.result_away_ht,
        "stake_units": _float_odds(row.stake_units),
        "profit_units": _float_odds(row.profit_units),
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
        "is_current": bool(row.is_current),
        "purchasability_v3": serialize_purchasability_from_activation(row, version="v3"),
        "purchasability_v31": serialize_purchasability_from_activation(row, version="v31"),
    }


def list_kpi_signal_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None = None,
    selection_key: str | None = None,
    normalized_market: str | None = None,
    evaluation_status: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    only_current: bool = True,
    limit: int = 200,
    offset: int = 0,
    purchasability_version: str | None = None,
    purchasability_status: str | None = None,
    purchasability_class: str | None = None,
    purchasability_score_min: float | None = None,
    purchasability_score_max: float | None = None,
    purchasability_quality: str | None = None,
) -> dict[str, Any]:
    validate_purchasability_filters(
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
    )
    query = _base_query(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
    ).order_by(
        CecchinoKpiSignalActivation.scan_date.desc(),
        CecchinoKpiSignalActivation.rating_score.desc(),
        CecchinoKpiSignalActivation.id.desc(),
    )
    total = int(
        db.scalar(
            _count_filters_kwargs(
                date_from=date_from,
                date_to=date_to,
                rating_bucket=rating_bucket,
                selection_key=selection_key,
                normalized_market=normalized_market,
                evaluation_status=evaluation_status,
                league_name=league_name,
                country_name=country_name,
                only_current=only_current,
                purchasability_version=purchasability_version,
                purchasability_status=purchasability_status,
                purchasability_class=purchasability_class,
                purchasability_score_min=purchasability_score_min,
                purchasability_score_max=purchasability_score_max,
                purchasability_quality=purchasability_quality,
            ),
        )
        or 0,
    )
    rows = list(db.scalars(query.offset(offset).limit(limit)).all())
    return {
        "status": "ok",
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": _filter_payload(
            date_from=date_from,
            date_to=date_to,
            rating_bucket=rating_bucket,
            selection_key=selection_key,
            normalized_market=normalized_market,
            evaluation_status=evaluation_status,
            league_name=league_name,
            country_name=country_name,
            only_current=only_current,
            purchasability_version=purchasability_version,
            purchasability_status=purchasability_status,
            purchasability_class=purchasability_class,
            purchasability_score_min=purchasability_score_min,
            purchasability_score_max=purchasability_score_max,
            purchasability_quality=purchasability_quality,
        ),
        "activations": [serialize_kpi_activation(r) for r in rows],
    }


def export_kpi_signals_csv(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    rating_bucket: str | None = None,
    selection_key: str | None = None,
    normalized_market: str | None = None,
    evaluation_status: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    only_current: bool = True,
    purchasability_version: str | None = None,
    purchasability_status: str | None = None,
    purchasability_class: str | None = None,
    purchasability_score_min: float | None = None,
    purchasability_score_max: float | None = None,
    purchasability_quality: str | None = None,
) -> str:
    payload = list_kpi_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        rating_bucket=rating_bucket,
        selection_key=selection_key,
        normalized_market=normalized_market,
        evaluation_status=evaluation_status,
        league_name=league_name,
        country_name=country_name,
        only_current=only_current,
        purchasability_version=purchasability_version,
        purchasability_status=purchasability_status,
        purchasability_class=purchasability_class,
        purchasability_score_min=purchasability_score_min,
        purchasability_score_max=purchasability_score_max,
        purchasability_quality=purchasability_quality,
        limit=10000,
        offset=0,
    )
    buffer = io.StringIO()
    fieldnames = [
        "scan_date",
        "home_team_name",
        "away_team_name",
        "league_name",
        "selection_label",
        "selection_key",
        "rating_score",
        "rating_bucket",
        "quota_book",
        "quota_cecchino",
        "edge_pct",
        "result_home_ht",
        "result_away_ht",
        "result_home_ft",
        "result_away_ft",
        "evaluation_status",
        "profit_units",
        "purchasability_v3_formula_version",
        "purchasability_v3_status",
        "purchasability_v3_score",
        "purchasability_v3_class",
        "purchasability_v3_calculation_quality",
        "purchasability_v3_source_snapshot_at",
        "purchasability_v3_reason_codes",
        "purchasability_v31_candidate_version",
        "purchasability_v31_formula_version",
        "purchasability_v31_registry_status",
        "purchasability_v31_status",
        "purchasability_v31_score",
        "purchasability_v31_class",
        "purchasability_v31_calculation_quality",
        "purchasability_v31_historical_evidence_quality",
        "purchasability_v31_source_snapshot_at",
        "purchasability_v31_execution_quote_real",
        "purchasability_v31_reason_codes",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in payload["activations"]:
        v3 = row.get("purchasability_v3") or {}
        v31 = row.get("purchasability_v31") or {}
        writer.writerow(
            {
                **row,
                "purchasability_v3_formula_version": v3.get("formula_version"),
                "purchasability_v3_status": v3.get("status"),
                "purchasability_v3_score": v3.get("score"),
                "purchasability_v3_class": v3.get("class_label") or v3.get("class_key"),
                "purchasability_v3_calculation_quality": v3.get("calculation_quality"),
                "purchasability_v3_source_snapshot_at": v3.get("source_snapshot_at"),
                "purchasability_v3_reason_codes": "|".join(v3.get("reason_codes") or []),
                "purchasability_v31_candidate_version": v31.get("candidate_version"),
                "purchasability_v31_formula_version": v31.get("formula_version"),
                "purchasability_v31_registry_status": v31.get("registry_status"),
                "purchasability_v31_status": v31.get("status"),
                "purchasability_v31_score": v31.get("score"),
                "purchasability_v31_class": v31.get("class_label") or v31.get("class_key"),
                "purchasability_v31_calculation_quality": v31.get("calculation_quality"),
                "purchasability_v31_historical_evidence_quality": v31.get(
                    "historical_evidence_quality"
                ),
                "purchasability_v31_source_snapshot_at": v31.get("source_snapshot_at"),
                "purchasability_v31_execution_quote_real": v31.get("execution_quote_real"),
                "purchasability_v31_reason_codes": "|".join(v31.get("reason_codes") or []),
            }
        )
    return buffer.getvalue()
