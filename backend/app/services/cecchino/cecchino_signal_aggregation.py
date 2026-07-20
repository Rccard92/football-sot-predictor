"""Aggregazioni statistiche segnali Cecchino."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, func, not_, or_, select
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
from app.services.cecchino.cecchino_constants import CECCHINO_DEFAULT_WEIGHT_MODEL_KEY, format_model_weights_display
from app.services.cecchino.cecchino_signal_display_order import (
    display_label_for_signal_group,
    signal_group_sort_key,
)
from app.services.cecchino.cecchino_signal_min_odds import get_min_book_odd
from app.services.cecchino.cecchino_signal_value_gate import VALUE_REASON_OK, signal_has_value_from_kpi_context


def _export_value_gate_fields(
    item: dict[str, Any],
    *,
    min_book_odds: dict | None = None,
) -> tuple[Any, str, str]:
    target_key = item.get("target_market_key")
    min_odd = get_min_book_odd(target_key, min_book_odds=min_book_odds)
    kpi_ctx = {
        "quota_book": item.get("quota_book"),
        "quota_cecchino": item.get("quota_cecchino"),
    }
    passed, reason, _meta = signal_has_value_from_kpi_context(
        kpi_ctx,
        target_market_key=target_key,
        min_book_odds=min_book_odds,
    )
    min_odd_display = float(min_odd) if min_odd is not None else ""
    return min_odd_display, "SI" if passed else "NO", reason if reason != VALUE_REASON_OK else ""


def _success_rate(won: int, lost: int) -> float | None:
    settled = won + lost
    if settled <= 0:
        return None
    return round((won / settled) * 100.0, 1)


def _format_signal_display_label(signal_group: str, signal_label: str) -> str:
    return display_label_for_signal_group(signal_group, signal_label)


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


def _bucket_counts(rows: list[Any]) -> dict[str, Any]:
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
    bucket = {
        "activations": len(rows),
        "settled": settled,
        "won": won,
        "lost": lost,
        "pending": pending,
        "not_evaluable": not_evaluable,
        "success_rate": _success_rate(won, lost),
    }
    return _enrich_taken_odds_metrics(bucket, rows)


def _float_odds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enrich_taken_odds_metrics(bucket: dict[str, Any], rows: list[Any]) -> dict[str, Any]:
    won = int(bucket.get("won") or 0)
    lost = int(bucket.get("lost") or 0)
    settled = won + lost

    won_with_odds = 0
    sum_won_book_odds = 0.0
    for row in rows:
        if row.evaluation_status != EVAL_WON:
            continue
        odds = _float_odds(getattr(row, "quota_book", None))
        if odds is None:
            continue
        won_with_odds += 1
        sum_won_book_odds += odds

    avg_won_book_odds = (
        round(sum_won_book_odds / won_with_odds, 2) if won_with_odds > 0 else None
    )
    win_rate = (won / settled) if settled > 0 else None
    quota_void = round(1.0 / win_rate, 2) if win_rate and win_rate > 0 else None
    void_margin = (
        round(avg_won_book_odds - quota_void, 2)
        if avg_won_book_odds is not None and quota_void is not None
        else None
    )
    taken_yield_index = (
        round(win_rate * avg_won_book_odds, 3)
        if win_rate is not None and avg_won_book_odds is not None
        else None
    )
    taken_profit_indicator = (
        round(taken_yield_index - 1.0, 3) if taken_yield_index is not None else None
    )

    return {
        **bucket,
        "won_with_odds": won_with_odds,
        "avg_won_book_odds": avg_won_book_odds,
        "quota_void": quota_void,
        "void_margin": void_margin,
        "taken_yield_index": taken_yield_index,
        "taken_profit_indicator": taken_profit_indicator,
    }


def _base_query(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    model_key: str | None = None,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
    all_models: bool = False,
):
    query = select(CecchinoSignalActivation).where(
        CecchinoSignalActivation.scan_date >= date_from,
        CecchinoSignalActivation.scan_date <= date_to,
        CecchinoSignalActivation.signal_value.is_(True),
    )
    # all_models=True means skip model_key filter entirely
    if not all_models and model_key:
        query = query.where(CecchinoSignalActivation.model_key == str(model_key).upper())
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
    query = query.where(
        not_(
            and_(
                CecchinoSignalActivation.source_column == "SCALA",
                or_(
                    CecchinoSignalActivation.signal_group == "HOME",
                    CecchinoSignalActivation.signal_group == "AWAY",
                ),
            ),
        ),
    )
    return query


def build_signals_summary(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    model_key: str | None = CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
    include_diagnostics: bool = False,
    all_models: bool = False,
) -> dict[str, Any]:
    # When all_models=True, model_key filter is skipped
    mk = None if all_models else str(model_key or CECCHINO_DEFAULT_WEIGHT_MODEL_KEY).upper()
    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "model_key": mk,
        "source_column": source_column,
        "signal_group": signal_group,
        "league_name": league_name,
        "country_name": country_name,
        "evaluation_status": evaluation_status,
        "only_current": only_current,
        "all_models": all_models,
    }
    rows = list(
        db.scalars(
            _base_query(
                db,
                date_from=date_from,
                date_to=date_to,
                model_key=mk,
                source_column=source_column,
                signal_group=signal_group,
                league_name=league_name,
                country_name=country_name,
                evaluation_status=evaluation_status,
                only_current=only_current,
                all_models=all_models,
            ),
        ).all(),
    )
    legacy_count_query = (
        select(func.count())
        .select_from(CecchinoSignalActivation)
        .where(
            CecchinoSignalActivation.scan_date >= date_from,
            CecchinoSignalActivation.scan_date <= date_to,
            CecchinoSignalActivation.model_key == mk,
            CecchinoSignalActivation.signal_value.is_(True),
            CecchinoSignalActivation.source_column == "SCALA",
            or_(
                CecchinoSignalActivation.signal_group == "HOME",
                CecchinoSignalActivation.signal_group == "AWAY",
            ),
        )
    )
    if only_current:
        legacy_count_query = legacy_count_query.where(CecchinoSignalActivation.is_current.is_(True))
    legacy_wrong_in_range = int(db.scalar(legacy_count_query) or 0)
    summary_warnings: list[str] = []
    if legacy_wrong_in_range:
        summary_warnings.append("legacy_wrong_scala_mapping_detected")

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
        for sg, items in sorted(by_signal_map.items(), key=lambda item: signal_group_sort_key(item[0]))
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
        for (sg, label, col), items in sorted(
            by_combo_map.items(),
            key=lambda item: (signal_group_sort_key(item[0][0]), item[0][2]),
        )
    ]

    result = {
        "filters": filters,
        "overall": overall,
        "by_signal": by_signal,
        "by_column": by_column,
        "by_signal_and_column": by_signal_and_column,
        "warnings": summary_warnings,
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
    model_key: str | None = CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
    limit: int = 100,
    offset: int = 0,
    all_models: bool = False,
) -> dict[str, Any]:
    # When all_models=True, model_key filter is skipped
    mk = None if all_models else str(model_key or CECCHINO_DEFAULT_WEIGHT_MODEL_KEY).upper()
    query = _base_query(
        db,
        date_from=date_from,
        date_to=date_to,
        model_key=mk,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
        all_models=all_models,
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


def _counts_in_avg_won_odds(row: CecchinoSignalActivation) -> bool:
    return row.evaluation_status == EVAL_WON and row.quota_book is not None


def _activation_source_cohort(
    activation_timestamp: str | None,
    kickoff: str | None,
) -> str | None:
    if not activation_timestamp or not kickoff:
        return None
    try:
        act_str = str(activation_timestamp).replace("Z", "+00:00")
        kick_str = str(kickoff).replace("Z", "+00:00")
        act_dt = datetime.fromisoformat(act_str)
        kick_dt = datetime.fromisoformat(kick_str)
        if act_dt.tzinfo is None:
            act_dt = act_dt.replace(tzinfo=timezone.utc)
        if kick_dt.tzinfo is None:
            kick_dt = kick_dt.replace(tzinfo=timezone.utc)
        return (
            "historical_persisted_verified"
            if act_dt < kick_dt
            else "unusable"
        )
    except (ValueError, TypeError):
        return None


def _serialize_activation_row(row: CecchinoSignalActivation) -> dict[str, Any]:
    home = row.home_team_name or "?"
    away = row.away_team_name or "?"
    ft_score = None
    if row.ft_home_goals is not None and row.ft_away_goals is not None:
        ft_score = f"{row.ft_home_goals}-{row.ft_away_goals}"
    ht_score = None
    if row.ht_home_goals is not None and row.ht_away_goals is not None:
        ht_score = f"{row.ht_home_goals}-{row.ht_away_goals}"
    
    # Activation timestamp (created_at)
    activation_timestamp = None
    if hasattr(row, "created_at") and row.created_at is not None:
        activation_timestamp = row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else str(row.created_at)
    
    # Evaluated at timestamp
    evaluated_at = None
    if hasattr(row, "evaluated_at") and row.evaluated_at is not None:
        evaluated_at = row.evaluated_at.isoformat() if hasattr(row.evaluated_at, "isoformat") else str(row.evaluated_at)
    
    # Weights version from model_key
    weights_version = getattr(row, "weights_version", None) or None
    
    # Probabilities: only persisted values (no reconstruction from odds)
    prob_cecchino = None
    if hasattr(row, "prob_cecchino") and row.prob_cecchino is not None:
        prob_cecchino = float(row.prob_cecchino)
    prob_book = None
    if hasattr(row, "prob_book") and row.prob_book is not None:
        prob_book = float(row.prob_book)

    selection = None
    selection_source = None
    if row.target_market_key:
        selection = row.target_market_key
        selection_source = "derived_from_target_market_key"

    source_cohort = _activation_source_cohort(activation_timestamp, (
        row.kickoff.isoformat() if row.kickoff else None
    ))

    return {
        "id": int(row.id),
        "today_fixture_id": int(row.today_fixture_id),
        "local_fixture_id": row.local_fixture_id,
        "provider_fixture_id": row.provider_fixture_id,
        "competition_id": None,
        "model_key": row.model_key,
        "model_label": row.model_label,
        "weights_version": weights_version,
        "weights_display": format_model_weights_display(row.model_key) if row.model_key else None,
        "scan_date": row.scan_date.isoformat(),
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "match": f"{home} vs {away}",
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
        "country_name": row.country_name,
        "league_name": row.league_name,
        "signal_group": row.signal_group,
        "signal_label": _format_signal_display_label(row.signal_group, row.signal_label),
        "selection": selection,
        "selection_source": selection_source,
        "source_column": row.source_column,
        "target_market_label": _format_target_market_label(row),
        "target_market_key": row.target_market_key,
        "source_cohort": source_cohort,
        "activation_status": None,
        "evaluation_status": row.evaluation_status,
        "evaluation_reason": row.evaluation_reason,
        "evaluated_at": evaluated_at,
        "result_home_ft": row.ft_home_goals,
        "result_away_ft": row.ft_away_goals,
        "result_home_ht": row.ht_home_goals,
        "result_away_ht": row.ht_away_goals,
        "ft_home_goals": row.ft_home_goals,
        "ft_away_goals": row.ft_away_goals,
        "ht_home_goals": row.ht_home_goals,
        "ht_away_goals": row.ht_away_goals,
        "ft_score": ft_score,
        "ht_score": ht_score,
        "quota_book": float(row.quota_book) if row.quota_book is not None else None,
        "quota_cecchino": float(row.quota_cecchino) if row.quota_cecchino is not None else None,
        "prob_book": prob_book,
        "prob_cecchino": prob_cecchino,
        "edge_pct": float(row.edge_pct) if row.edge_pct is not None else None,
        "rating": row.rating,
        "score": None,
        "stake_units": None,
        "profit_units": None,
        "warning_codes": None,
        "is_current": row.is_current,
        "activation_timestamp": activation_timestamp,
        "counts_in_avg_won_odds": _counts_in_avg_won_odds(row),
    }


def export_signals_csv(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    model_key: str | None = CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    source_column: str | None = None,
    signal_group: str | None = None,
    league_name: str | None = None,
    country_name: str | None = None,
    evaluation_status: str | None = None,
    only_current: bool = True,
) -> str:
    from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
        load_signal_min_book_odds,
    )

    min_book_odds = load_signal_min_book_odds(db)
    mk = str(model_key or CECCHINO_DEFAULT_WEIGHT_MODEL_KEY).upper()
    payload = list_signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        model_key=mk,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
        limit=100_000,
        offset=0,
    )
    summary = build_signals_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        model_key=mk,
        source_column=source_column,
        signal_group=signal_group,
        league_name=league_name,
        country_name=country_name,
        evaluation_status=evaluation_status,
        only_current=only_current,
    )
    overall = summary.get("overall") or {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Data",
            "Ora",
            "Match",
            "Nazione",
            "Campionato",
            "Modello",
            "Pesi modello",
            "Segnale",
            "Colonna",
            "Target",
            "Stato valutazione",
            "Esito",
            "HT",
            "FT",
            "Quota Book",
            "Quota conteggiata in media prese",
            "Quota Cecchino",
            "Soglia min book",
            "Soglia min superata",
            "Value gate reason",
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
        counts_in_avg = "SI" if item.get("counts_in_avg_won_odds") else "NO"
        min_odd_display, min_odd_passed, value_gate_reason = _export_value_gate_fields(
            item,
            min_book_odds=min_book_odds,
        )
        writer.writerow(
            [
                kickoff_date,
                kickoff_time,
                item.get("match"),
                item.get("country_name"),
                item.get("league_name"),
                item.get("model_label") or item.get("model_key"),
                item.get("weights_display"),
                item.get("signal_label"),
                item.get("source_column"),
                item.get("target_market_label"),
                item.get("evaluation_status"),
                esito_label,
                item.get("ht_score"),
                item.get("ft_score"),
                item.get("quota_book"),
                counts_in_avg,
                item.get("quota_cecchino"),
                min_odd_display,
                min_odd_passed,
                value_gate_reason,
                item.get("edge_pct"),
                item.get("rating"),
                item.get("evaluation_reason"),
            ],
        )
    writer.writerow([])
    writer.writerow(
        [
            "SUMMARY",
            "",
            "",
            "",
            "",
            mk,
            format_model_weights_display(mk),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            overall.get("avg_won_book_odds"),
            overall.get("quota_void"),
            overall.get("taken_profit_indicator"),
            "",
        ],
    )
    return output.getvalue()
