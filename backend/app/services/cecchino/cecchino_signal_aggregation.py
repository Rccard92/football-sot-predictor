"""Aggregazioni statistiche segnali Cecchino."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    CecchinoSignalActivation,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture


def _success_rate(won: int, lost: int) -> float | None:
    settled = won + lost
    if settled <= 0:
        return None
    return round((won / settled) * 100.0, 1)


def _format_signal_display_label(signal_group: str, signal_label: str) -> str:
    if signal_group == "UNDER_UNDER_PT":
        return "UNDER 2.5"
    if signal_group == "OVER_OVER_PT":
        return "OVER 2.5"
    return signal_label


def _count_eligible_fixtures(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    league_name: str | None = None,
    country_name: str | None = None,
) -> int:
    query = select(func.count()).select_from(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if league_name:
        query = query.where(CecchinoTodayFixture.league_name == league_name)
    if country_name:
        query = query.where(CecchinoTodayFixture.country_name == country_name)
    return int(db.scalar(query) or 0)


def _enrich_overall_metrics(
    db: Session,
    overall: dict[str, Any],
    rows: list[Any],
    *,
    date_from: date,
    date_to: date,
    league_name: str | None = None,
    country_name: str | None = None,
) -> dict[str, Any]:
    fixtures_with_signals_count = len({int(r.today_fixture_id) for r in rows if r.today_fixture_id is not None})
    eligible_fixtures_count = _count_eligible_fixtures(
        db,
        date_from=date_from,
        date_to=date_to,
        league_name=league_name,
        country_name=country_name,
    )
    denominator = eligible_fixtures_count if eligible_fixtures_count > 0 else fixtures_with_signals_count
    activations = int(overall.get("activations") or 0)
    avg_signals_per_fixture = (
        round(activations / denominator, 1) if denominator > 0 else None
    )
    return {
        **overall,
        "eligible_fixtures_count": eligible_fixtures_count,
        "fixtures_with_signals_count": fixtures_with_signals_count,
        "avg_signals_per_fixture": avg_signals_per_fixture,
    }


def _bucket_counts(rows: list[Any]) -> dict[str, int]:
    won = lost = pending = not_evaluable = 0
    for row in rows:
        status = row.evaluation_status
        if status == EVAL_WON:
            won += 1
        elif status == EVAL_LOST:
            lost += 1
        elif status in (EVAL_PENDING, EVAL_RESULT_MISSING):
            pending += 1
        elif status == EVAL_NOT_EVALUABLE:
            not_evaluable += 1
    settled = won + lost
    return {
        "activations": len(rows),
        "settled": settled,
        "won": won,
        "lost": lost,
        "pending": pending,
        "not_evaluable": not_evaluable,
        "success_rate": _success_rate(won, lost),
    }


def _base_query(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
):
    query = select(CecchinoSignalActivation).where(
        CecchinoSignalActivation.scan_date >= date_from,
        CecchinoSignalActivation.scan_date <= date_to,
        CecchinoSignalActivation.signal_value.is_(True),
    )
    if only_current:
        query = query.where(CecchinoSignalActivation.is_current.is_(True))
    if source_column:
        query = query.where(CecchinoSignalActivation.source_column == source_column)
    if signal_group:
        query = query.where(CecchinoSignalActivation.signal_group == signal_group)
    if league_name:
        query = query.where(CecchinoSignalActivation.league_name == league_name)
    if country_name:
        query = query.where(CecchinoSignalActivation.country_name == country_name)
    if evaluation_status:
        query = query.where(CecchinoSignalActivation.evaluation_status == evaluation_status)
    return query


def build_signals_summary(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "source_column": source_column,
        "signal_group": signal_group,
        "league_name": league_name,
        "country_name": country_name,
        "evaluation_status": evaluation_status,
        "only_current": only_current,
    }
    rows = list(
        db.scalars(
            _base_query(
                db,
                date_from=date_from,
                date_to=date_to,
                source_column=source_column,
                signal_group=signal_group,
                league_name=league_name,
                country_name=country_name,
                evaluation_status=evaluation_status,
                only_current=only_current,
            ),
        ).all(),
    )
    overall = _enrich_overall_metrics(
        db,
        _bucket_counts(rows),
        rows,
        date_from=date_from,
        date_to=date_to,
        league_name=league_name,
        country_name=country_name,
    )

    by_signal_map: dict[str, list[Any]] = {}
    by_column_map: dict[str, list[Any]] = {}
    by_combo_map: dict[tuple[str, str, str], list[Any]] = {}

    for row in rows:
        by_signal_map.setdefault(row.signal_group, []).append(row)
        by_column_map.setdefault(row.source_column, []).append(row)
        combo_key = (row.signal_group, row.signal_label, row.source_column)
        by_combo_map.setdefault(combo_key, []).append(row)

    by_signal = [
        {
            "signal_group": sg,
            "signal_label": _format_signal_display_label(sg, items[0].signal_label),
            **_bucket_counts(items),
        }
        for sg, items in sorted(by_signal_map.items())
    ]
    by_column = [
        {"source_column": col, **_bucket_counts(items)}
        for col, items in sorted(by_column_map.items())
    ]
    by_signal_and_column = [
        {
            "signal_group": sg,
            "signal_label": _format_signal_display_label(sg, label),
            "source_column": col,
            **_bucket_counts(items),
        }
        for (sg, label, col), items in sorted(by_combo_map.items())
    ]

    result = {
        "filters": filters,
        "overall": overall,
        "by_signal": by_signal,
        "by_column": by_column,
        "by_signal_and_column": by_signal_and_column,
    }
    if include_diagnostics:
        from app.services.cecchino.cecchino_signal_backfill import build_signal_diagnostics

        result["diagnostics"] = build_signal_diagnostics(
            db,
            date_from=date_from,
            date_to=date_to,
        )
    return result


def list_signal_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = _base_query(
        db,
        date_from=date_from,
        date_to=date_to,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(
                CecchinoSignalActivation.scan_date.desc(),
                CecchinoSignalActivation.kickoff.desc().nullslast(),
                CecchinoSignalActivation.id.desc(),
            ).offset(offset).limit(limit),
        ).all(),
    )
    items = [_serialize_activation_row(row) for row in rows]
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


def _format_target_market_label(row: CecchinoSignalActivation) -> str | None:
    if row.signal_group == "UNDER_UNDER_PT":
        return "Under 2.5 FT"
    if row.signal_group == "OVER_OVER_PT":
        return "Over 2.5 FT"
    return row.target_market_label


def _serialize_activation_row(row: CecchinoSignalActivation) -> dict[str, Any]:
    home = row.home_team_name or "?"
    away = row.away_team_name or "?"
    ft_score = None
    if row.ft_home_goals is not None and row.ft_away_goals is not None:
        ft_score = f"{row.ft_home_goals}-{row.ft_away_goals}"
    ht_score = None
    if row.ht_home_goals is not None and row.ht_away_goals is not None:
        ht_score = f"{row.ht_home_goals}-{row.ht_away_goals}"
    return {
        "id": int(row.id),
        "today_fixture_id": int(row.today_fixture_id),
        "scan_date": row.scan_date.isoformat(),
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "match": f"{home} vs {away}",
        "country_name": row.country_name,
        "league_name": row.league_name,
        "signal_group": row.signal_group,
        "signal_label": _format_signal_display_label(row.signal_group, row.signal_label),
        "source_column": row.source_column,
        "target_market_label": _format_target_market_label(row),
        "evaluation_status": row.evaluation_status,
        "evaluation_reason": row.evaluation_reason,
        "ft_score": ft_score,
        "ht_score": ht_score,
        "quota_book": float(row.quota_book) if row.quota_book is not None else None,
        "quota_cecchino": float(row.quota_cecchino) if row.quota_cecchino is not None else None,
        "edge_pct": float(row.edge_pct) if row.edge_pct is not None else None,
        "rating": row.rating,
        "is_current": row.is_current,
    }


def export_signals_csv(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
) -> str:
    payload = list_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
        limit=100_000,
        offset=0,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Data",
            "Ora",
            "Match",
            "Nazione",
            "Campionato",
            "Segnale",
            "Colonna",
            "Target",
            "Stato valutazione",
            "Esito",
            "HT",
            "FT",
            "Quota Book",
            "Quota Cecchino",
            "Edge",
            "Rating",
            "Motivo valutazione",
        ],
    )
    for item in payload["items"]:
        kickoff = item.get("kickoff") or ""
        kickoff_date = kickoff[:10] if kickoff else item.get("scan_date")
        kickoff_time = kickoff[11:16] if len(kickoff) >= 16 else ""
        esito = item["evaluation_status"]
        if esito == EVAL_WON:
            esito_label = "Vinto"
        elif esito == EVAL_LOST:
            esito_label = "Perso"
        elif esito in (EVAL_PENDING, EVAL_RESULT_MISSING):
            esito_label = "Pending"
        elif esito == EVAL_NOT_EVALUABLE:
            esito_label = "Non valutabile"
        else:
            esito_label = esito
        writer.writerow(
            [
                kickoff_date,
                kickoff_time,
                item.get("match"),
                item.get("country_name"),
                item.get("league_name"),
                item.get("signal_label"),
                item.get("source_column"),
                item.get("target_market_label"),
                item.get("evaluation_status"),
                esito_label,
                item.get("ht_score"),
                item.get("ft_score"),
                item.get("quota_book"),
                item.get("quota_cecchino"),
                item.get("edge_pct"),
                item.get("rating"),
                item.get("evaluation_reason"),
            ],
        )
    return output.getvalue()
