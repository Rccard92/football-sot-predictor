"""Sync idempotente segnali SI dalla matrice Cecchino."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import CecchinoSignalActivation
from app.models.cecchino_today_fixture import CecchinoTodayFixture, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    STATUS_AVAILABLE,
    model_meta_for_key,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    apply_evaluation_to_activation,
    evaluate_signal_activation,
    match_result_from_fixture,
)
from app.services.cecchino.cecchino_signal_target_mapping import (
    LEGACY_WRONG_SCALA_REASON,
    is_valid_scala_activation,
    map_column_to_source,
    map_cecchino_signal_to_target,
    map_row_key_to_signal_group,
)
from app.services.cecchino.cecchino_signal_odds_refresh import resolve_kpi_odds_for_activation


def _num(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def _activation_pair_key(model_key: str, signal_group: str, source_column: str) -> tuple[str, str, str]:
    return (model_key, signal_group, source_column)


def _iter_si_cells(signals_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = signals_matrix.get("rows") or []
    if not isinstance(rows, list):
        return []
    cells: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("key") or "")
        signal_group = map_row_key_to_signal_group(row_key)
        if not signal_group:
            continue
        signals = row.get("signals") or {}
        if not isinstance(signals, dict):
            continue
        for column_key, raw_value in signals.items():
            if str(raw_value).upper() != "SI":
                continue
            source_column = map_column_to_source(str(column_key))
            if not source_column:
                continue
            if not is_valid_scala_activation(signal_group, source_column):
                continue
            cells.append(
                {
                    "row_key": row_key,
                    "signal_group": signal_group,
                    "signal_label": str(row.get("label") or row_key),
                    "source_column": source_column,
                    "column_key": str(column_key),
                    "raw_signal_value": "SI",
                },
            )
    return cells


def sync_cecchino_signal_activations(
    db: Session,
    today_fixture_id: int,
    *,
    model_key: str = CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    signals_matrix: dict[str, Any] | None = None,
    model_meta: dict[str, object] | None = None,
) -> dict[str, int]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"created": 0, "updated": 0, "deactivated": 0, "skipped": 1}

    mk = str(model_key).upper()
    meta = model_meta or model_meta_for_key(mk)

    output = row.cecchino_output_json or {}
    if signals_matrix is None:
        signals_matrix = output.get("signals_matrix") if isinstance(output, dict) else None
    if not isinstance(signals_matrix, dict) or signals_matrix.get("status") != STATUS_AVAILABLE:
        return {"created": 0, "updated": 0, "deactivated": 0, "skipped": 1}

    kpi_panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    inputs = signals_matrix.get("inputs") or {}
    si_cells = _iter_si_cells(signals_matrix)
    active_keys: set[tuple[str, str, str]] = set()

    existing = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.today_fixture_id == int(today_fixture_id),
                CecchinoSignalActivation.model_key == mk,
            ),
        ).all(),
    )
    by_key: dict[tuple[str, str, str], CecchinoSignalActivation] = {}
    for activation in existing:
        by_key[
            _activation_pair_key(activation.model_key, activation.signal_group, activation.source_column)
        ] = activation

    counts = {"created": 0, "updated": 0, "deactivated": 0, "skipped": 0}
    match_result = match_result_from_fixture(row)

    for cell in si_cells:
        target = map_cecchino_signal_to_target(cell["signal_group"], cell["source_column"])
        kpi_ctx = resolve_kpi_odds_for_activation(
            kpi_panel,
            signal_group=cell["signal_group"],
            target_market_key=target.get("target_market_key"),
        )
        key = _activation_pair_key(mk, cell["signal_group"], cell["source_column"])
        active_keys.add(key)
        activation = by_key.get(key)

        if activation is None:
            activation = CecchinoSignalActivation(
                today_fixture_id=int(row.id),
                local_fixture_id=row.local_fixture_id,
                provider_source=row.provider_source or PROVIDER_API_FOOTBALL,
                provider_fixture_id=int(row.provider_fixture_id),
                scan_date=row.scan_date,
                kickoff=row.kickoff,
                country_name=row.country_name,
                league_name=row.league_name,
                home_team_name=row.home_team_name,
                away_team_name=row.away_team_name,
                model_key=mk,
                model_label=str(meta.get("model_label") or ""),
                weights_version=str(meta.get("weights_version") or ""),
                weights_json=meta.get("weights_json") if isinstance(meta.get("weights_json"), dict) else None,
                signal_group=cell["signal_group"],
                signal_label=cell["signal_label"],
                source_column=cell["source_column"],
                signal_value=True,
                raw_signal_value=cell["raw_signal_value"],
                f32=_num(inputs.get("q1")),
                f33=_num(inputs.get("qx")),
                f34=_num(inputs.get("q2")),
                f35=_num(inputs.get("avg_q")),
                f36=_num(inputs.get("diff_1_2")),
                target_market_key=target["target_market_key"],
                target_market_label=target["target_market_label"],
                target_period=target["target_period"],
                evaluation_status=target["evaluation_status"],
                evaluation_reason=target["evaluation_reason"],
                quota_book=_num(kpi_ctx.get("quota_book")),
                quota_cecchino=_num(kpi_ctx.get("quota_cecchino")),
                prob_book=_num(kpi_ctx.get("prob_book")),
                prob_cecchino=_num(kpi_ctx.get("prob_cecchino")),
                edge_pct=_num(kpi_ctx.get("edge_pct")),
                rating=int(kpi_ctx["rating"]) if kpi_ctx.get("rating") is not None else None,
                is_current=True,
                deactivated_at=None,
            )
            db.add(activation)
            by_key[key] = activation
            counts["created"] += 1
        else:
            activation.signal_value = True
            activation.raw_signal_value = "SI"
            activation.is_current = True
            activation.deactivated_at = None
            activation.model_label = str(meta.get("model_label") or activation.model_label or "")
            activation.weights_version = str(meta.get("weights_version") or activation.weights_version or "")
            if isinstance(meta.get("weights_json"), dict):
                activation.weights_json = meta["weights_json"]
            activation.target_market_key = target["target_market_key"]
            activation.target_market_label = target["target_market_label"]
            activation.target_period = target["target_period"]
            if activation.evaluation_status == "not_evaluable" and target.get("target_market_key"):
                activation.evaluation_status = target["evaluation_status"]
                activation.evaluation_reason = target["evaluation_reason"]
            activation.f32 = _num(inputs.get("q1"))
            activation.f33 = _num(inputs.get("qx"))
            activation.f34 = _num(inputs.get("q2"))
            activation.f35 = _num(inputs.get("avg_q"))
            activation.f36 = _num(inputs.get("diff_1_2"))
            activation.quota_book = _num(kpi_ctx.get("quota_book"))
            activation.quota_cecchino = _num(kpi_ctx.get("quota_cecchino"))
            activation.prob_book = _num(kpi_ctx.get("prob_book"))
            activation.prob_cecchino = _num(kpi_ctx.get("prob_cecchino"))
            activation.edge_pct = _num(kpi_ctx.get("edge_pct"))
            activation.rating = int(kpi_ctx["rating"]) if kpi_ctx.get("rating") is not None else None
            counts["updated"] += 1

        if activation.target_market_key:
            eval_result = evaluate_signal_activation(activation, match_result)
            apply_evaluation_to_activation(activation, eval_result, result_status=row.match_display_status)

    now = datetime.now(timezone.utc)
    for activation in existing:
        key = _activation_pair_key(activation.model_key, activation.signal_group, activation.source_column)
        if key not in active_keys and activation.is_current:
            activation.is_current = False
            activation.deactivated_at = now
            counts["deactivated"] += 1

    db.flush()
    return counts


def remap_legacy_scala_activations_in_range(db: Session, *, date_from, date_to) -> int:
    """Disattiva activation HOME/AWAY+SCALA errate (mapping pre-Fase 37/38)."""
    from sqlalchemy import and_, or_, select

    rows = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.scan_date >= date_from,
                CecchinoSignalActivation.scan_date <= date_to,
                CecchinoSignalActivation.is_current.is_(True),
                or_(
                    and_(
                        CecchinoSignalActivation.signal_group == "HOME",
                        CecchinoSignalActivation.source_column == "SCALA",
                    ),
                    and_(
                        CecchinoSignalActivation.signal_group == "AWAY",
                        CecchinoSignalActivation.source_column == "SCALA",
                    ),
                ),
            ),
        ).all(),
    )
    if not rows:
        return 0

    now = datetime.now(timezone.utc)
    for activation in rows:
        activation.is_current = False
        activation.deactivated_at = now
        activation.evaluation_reason = LEGACY_WRONG_SCALA_REASON
    db.flush()
    return len(rows)
