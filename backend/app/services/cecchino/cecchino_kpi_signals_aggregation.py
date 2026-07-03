"""Aggregazioni statistiche Segnali KPI."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

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
    MIN_KPI_RATING,
    RATING_BUCKETS,
    extract_kpi_rating_score,
    normalize_kpi_row,
)


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

    created = int(
        db.scalar(
            select(func.count())
            .select_from(CecchinoKpiSignalActivation)
            .where(
                CecchinoKpiSignalActivation.scan_date >= date_from,
                CecchinoKpiSignalActivation.scan_date <= date_to,
                CecchinoKpiSignalActivation.is_current.is_(True),
            ),
        )
        or 0,
    )
    return {
        "today_fixtures_count": len(fixtures),
        "fixtures_with_kpi_panel": fixtures_with_kpi,
        "kpi_rows_seen": kpi_rows_seen,
        "kpi_signals_created": created,
        "kpi_rows_below_50": below_50,
        "kpi_rows_without_book_odds": without_book,
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
) -> dict[str, Any]:
    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "rating_bucket": rating_bucket,
        "selection_key": selection_key,
        "normalized_market": normalized_market,
        "evaluation_status": evaluation_status,
        "league_name": league_name,
        "country_name": country_name,
        "only_current": only_current,
    }
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
) -> dict[str, Any]:
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
    ).order_by(
        CecchinoKpiSignalActivation.scan_date.desc(),
        CecchinoKpiSignalActivation.rating_score.desc(),
        CecchinoKpiSignalActivation.id.desc(),
    )
    total = int(
        db.scalar(
            select(func.count()).select_from(CecchinoKpiSignalActivation).where(
                CecchinoKpiSignalActivation.scan_date >= date_from,
                CecchinoKpiSignalActivation.scan_date <= date_to,
                *([CecchinoKpiSignalActivation.is_current.is_(True)] if only_current else []),
                *([CecchinoKpiSignalActivation.rating_bucket == rating_bucket] if rating_bucket else []),
                *([CecchinoKpiSignalActivation.selection_key == selection_key] if selection_key else []),
                *([CecchinoKpiSignalActivation.normalized_market == normalized_market] if normalized_market else []),
                *([CecchinoKpiSignalActivation.evaluation_status == evaluation_status] if evaluation_status else []),
                *([CecchinoKpiSignalActivation.league_name == league_name] if league_name else []),
                *([CecchinoKpiSignalActivation.country_name == country_name] if country_name else []),
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
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in payload["activations"]:
        writer.writerow(row)
    return buffer.getvalue()
