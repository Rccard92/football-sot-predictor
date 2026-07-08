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
    DRAW_PT_PARENT_DEACTIVATED_REASON,
    LEGACY_WRONG_SCALA_REASON,
    build_draw_pt_derived_reason,
    is_valid_scala_activation,
    map_column_to_source,
    map_cecchino_signal_to_target,
    map_draw_pt_derived_target,
    map_row_key_to_signal_group,
)
from app.services.cecchino.cecchino_signal_min_odds import get_min_book_odd
from app.services.cecchino.cecchino_signal_odds_refresh import resolve_kpi_odds_for_activation
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT
from app.services.cecchino.cecchino_signal_value_gate import (
    VALUE_REASON_BOOK_BELOW_MIN,
    deactivation_reason_for_value_gate,
    empty_sync_value_counters,
    signal_has_value_from_kpi_context,
)


def _num(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def _activation_pair_key(model_key: str, signal_group: str, source_column: str) -> tuple[str, str, str]:
    return (model_key, signal_group, source_column)


def _empty_sync_counts() -> dict[str, int]:
    return {
        "created": 0,
        "updated": 0,
        "deactivated": 0,
        "skipped": 0,
        **empty_sync_value_counters(),
    }


def _deactivate_activation(
    activation: CecchinoSignalActivation,
    *,
    reason: str,
    now: datetime,
) -> None:
    activation.is_current = False
    activation.deactivated_at = now
    activation.evaluation_reason = reason


def _record_no_value_skip(counts: dict[str, int], reason: str) -> None:
    counts["no_value_skipped"] += 1
    if reason == "missing_quota_book":
        counts["missing_book_quote_skipped"] += 1
    elif reason == "missing_quota_cecchino":
        counts["missing_cecchino_quote_skipped"] += 1
    elif reason in ("invalid_quota_book", "invalid_quota_cecchino"):
        counts["invalid_quote_skipped"] += 1
    elif reason == VALUE_REASON_BOOK_BELOW_MIN:
        counts["min_book_odd_skipped"] += 1


def _record_value_threshold_applied(counts: dict[str, int], target_market_key: str | None) -> None:
    if get_min_book_odd(target_market_key) is not None:
        counts["min_book_odd_threshold_applied"] += 1


def _record_deactivation_for_value_reason(counts: dict[str, int], value_reason: str) -> None:
    if value_reason == VALUE_REASON_BOOK_BELOW_MIN:
        counts["deactivated_min_book_odd"] += 1
    else:
        counts["deactivated_no_value"] += 1


def _deactivate_draw_pair(
    *,
    mk: str,
    source_column: str,
    by_key: dict[tuple[str, str, str], CecchinoSignalActivation],
    counts: dict[str, int],
    reason: str,
    now: datetime,
) -> None:
    deactivation_reason = deactivation_reason_for_value_gate(reason)
    for signal_group in ("DRAW", "DRAW_PT"):
        activation = by_key.get(_activation_pair_key(mk, signal_group, source_column))
        if activation is None or not activation.is_current:
            continue
        if signal_group == "DRAW_PT":
            pt_reason = DRAW_PT_PARENT_DEACTIVATED_REASON
        else:
            pt_reason = deactivation_reason
        _deactivate_activation(activation, reason=pt_reason, now=now)
        if signal_group == "DRAW":
            _record_deactivation_for_value_reason(counts, reason)
        else:
            counts["draw_pt_deactivated"] += 1
            counts["derived_observations_deactivated"] += 1


def _upsert_activation(
    *,
    row: CecchinoTodayFixture,
    mk: str,
    meta: dict[str, object],
    cell: dict[str, Any],
    target: dict[str, Any],
    kpi_ctx: dict[str, Any],
    inputs: dict[str, Any],
    by_key: dict[tuple[str, str, str], CecchinoSignalActivation],
    db: Session,
    counts: dict[str, int],
    include_odds: bool = True,
    derived_reason: str | None = None,
) -> CecchinoSignalActivation:
    key = _activation_pair_key(mk, cell["signal_group"], cell["source_column"])
    activation = by_key.get(key)
    quota_book = _num(kpi_ctx.get("quota_book")) if include_odds else None
    quota_cecchino = _num(kpi_ctx.get("quota_cecchino")) if include_odds else None

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
            evaluation_reason=derived_reason or target["evaluation_reason"],
            quota_book=quota_book,
            quota_cecchino=quota_cecchino,
            prob_book=_num(kpi_ctx.get("prob_book")) if include_odds else None,
            prob_cecchino=_num(kpi_ctx.get("prob_cecchino")) if include_odds else None,
            edge_pct=_num(kpi_ctx.get("edge_pct")) if include_odds else None,
            rating=int(kpi_ctx["rating"]) if include_odds and kpi_ctx.get("rating") is not None else None,
            is_current=True,
            deactivated_at=None,
        )
        db.add(activation)
        by_key[key] = activation
        counts["created"] += 1
        if cell["signal_group"] == "DRAW_PT":
            counts["draw_pt_created"] += 1
            counts["derived_observations_created"] += 1
        return activation

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
        activation.evaluation_reason = derived_reason or target["evaluation_reason"]
    elif derived_reason:
        activation.evaluation_reason = derived_reason
    activation.f32 = _num(inputs.get("q1"))
    activation.f33 = _num(inputs.get("qx"))
    activation.f34 = _num(inputs.get("q2"))
    activation.f35 = _num(inputs.get("avg_q"))
    activation.f36 = _num(inputs.get("diff_1_2"))
    if include_odds:
        activation.quota_book = quota_book
        activation.quota_cecchino = quota_cecchino
        activation.prob_book = _num(kpi_ctx.get("prob_book"))
        activation.prob_cecchino = _num(kpi_ctx.get("prob_cecchino"))
        activation.edge_pct = _num(kpi_ctx.get("edge_pct"))
        activation.rating = int(kpi_ctx["rating"]) if kpi_ctx.get("rating") is not None else None
    else:
        activation.quota_book = None
        activation.quota_cecchino = None
        activation.prob_book = None
        activation.prob_cecchino = None
        activation.edge_pct = None
        activation.rating = None
    counts["updated"] += 1
    if cell["signal_group"] == "DRAW_PT":
        counts["draw_pt_updated"] += 1
    return activation


def _sync_draw_pt_derived(
    *,
    row: CecchinoTodayFixture,
    mk: str,
    meta: dict[str, object],
    cell: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    inputs: dict[str, Any],
    by_key: dict[tuple[str, str, str], CecchinoSignalActivation],
    db: Session,
    counts: dict[str, int],
    active_keys: set[tuple[str, str, str]],
    match_result: dict[str, Any],
) -> None:
    pt_kpi_ctx = resolve_kpi_odds_for_activation(
        kpi_panel,
        signal_group="DRAW_PT",
        target_market_key=SEL_DRAW_PT,
    )
    pt_passed, pt_reason, pt_value_meta = signal_has_value_from_kpi_context(
        pt_kpi_ctx,
        target_market_key=SEL_DRAW_PT,
    )
    _record_value_threshold_applied(counts, SEL_DRAW_PT)
    pt_key = _activation_pair_key(mk, "DRAW_PT", cell["source_column"])
    existing_pt = by_key.get(pt_key)

    if not pt_passed:
        _record_no_value_skip(counts, pt_reason)
        if existing_pt is not None and existing_pt.is_current:
            _deactivate_activation(
                existing_pt,
                reason=deactivation_reason_for_value_gate(pt_reason),
                now=datetime.now(timezone.utc),
            )
            counts["draw_pt_deactivated"] += 1
            counts["derived_observations_deactivated"] += 1
            if pt_reason == VALUE_REASON_BOOK_BELOW_MIN:
                counts["deactivated_min_book_odd"] += 1
        return

    counts["value_passed"] += 1
    active_keys.add(pt_key)
    pt_target = map_draw_pt_derived_target()
    pt_cell = {
        **cell,
        "signal_group": "DRAW_PT",
        "signal_label": "X PT",
    }
    derived_reason = build_draw_pt_derived_reason(
        quota_book=pt_value_meta.get("quota_book"),
        quota_cecchino=pt_value_meta.get("quota_cecchino"),
    )
    pt_activation = _upsert_activation(
        row=row,
        mk=mk,
        meta=meta,
        cell=pt_cell,
        target=pt_target,
        kpi_ctx=pt_kpi_ctx,
        inputs=inputs,
        by_key=by_key,
        db=db,
        counts=counts,
        include_odds=True,
        derived_reason=derived_reason,
    )
    if pt_activation.target_market_key:
        eval_result = evaluate_signal_activation(pt_activation, match_result)
        apply_evaluation_to_activation(pt_activation, eval_result, result_status=row.match_display_status)
        if eval_result["evaluation_status"] in ("won", "lost"):
            counts["draw_pt_evaluated"] = counts.get("draw_pt_evaluated", 0) + 1


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
        return {**_empty_sync_counts(), "skipped": 1}

    mk = str(model_key).upper()
    meta = model_meta or model_meta_for_key(mk)

    output = row.cecchino_output_json or {}
    if signals_matrix is None:
        signals_matrix = output.get("signals_matrix") if isinstance(output, dict) else None
    if not isinstance(signals_matrix, dict) or signals_matrix.get("status") != STATUS_AVAILABLE:
        return {**_empty_sync_counts(), "skipped": 1}

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

    counts = _empty_sync_counts()
    match_result = match_result_from_fixture(row)
    now = datetime.now(timezone.utc)

    for cell in si_cells:
        counts["si_cells_seen"] += 1
        target = map_cecchino_signal_to_target(cell["signal_group"], cell["source_column"])
        kpi_ctx = resolve_kpi_odds_for_activation(
            kpi_panel,
            signal_group=cell["signal_group"],
            target_market_key=target.get("target_market_key"),
        )
        target_market_key = target.get("target_market_key")
        passed, value_reason, _value_meta = signal_has_value_from_kpi_context(
            kpi_ctx,
            target_market_key=target_market_key,
        )
        _record_value_threshold_applied(counts, target_market_key)
        key = _activation_pair_key(mk, cell["signal_group"], cell["source_column"])

        if cell["signal_group"] == "DRAW":
            if not passed:
                _record_no_value_skip(counts, value_reason)
                _deactivate_draw_pair(
                    mk=mk,
                    source_column=cell["source_column"],
                    by_key=by_key,
                    counts=counts,
                    reason=value_reason,
                    now=now,
                )
                continue

            counts["value_passed"] += 1
            active_keys.add(key)
            activation = _upsert_activation(
                row=row,
                mk=mk,
                meta=meta,
                cell=cell,
                target=target,
                kpi_ctx=kpi_ctx,
                inputs=inputs,
                by_key=by_key,
                db=db,
                counts=counts,
            )
            if activation.target_market_key:
                eval_result = evaluate_signal_activation(activation, match_result)
                apply_evaluation_to_activation(activation, eval_result, result_status=row.match_display_status)
            _sync_draw_pt_derived(
                row=row,
                mk=mk,
                meta=meta,
                cell=cell,
                kpi_panel=kpi_panel,
                inputs=inputs,
                by_key=by_key,
                db=db,
                counts=counts,
                active_keys=active_keys,
                match_result=match_result,
            )
            continue

        activation = by_key.get(key)

        if not passed:
            _record_no_value_skip(counts, value_reason)
            if activation is not None and activation.is_current:
                _deactivate_activation(
                    activation,
                    reason=deactivation_reason_for_value_gate(value_reason),
                    now=now,
                )
                _record_deactivation_for_value_reason(counts, value_reason)
            continue

        counts["value_passed"] += 1
        active_keys.add(key)
        activation = _upsert_activation(
            row=row,
            mk=mk,
            meta=meta,
            cell=cell,
            target=target,
            kpi_ctx=kpi_ctx,
            inputs=inputs,
            by_key=by_key,
            db=db,
            counts=counts,
        )
        if activation.target_market_key:
            eval_result = evaluate_signal_activation(activation, match_result)
            apply_evaluation_to_activation(activation, eval_result, result_status=row.match_display_status)

    for activation in existing:
        key = _activation_pair_key(activation.model_key, activation.signal_group, activation.source_column)
        if key not in active_keys and activation.is_current:
            activation.is_current = False
            activation.deactivated_at = now
            counts["deactivated"] += 1
            if activation.signal_group == "DRAW_PT":
                counts["draw_pt_deactivated"] += 1
                counts["derived_observations_deactivated"] += 1
                activation.evaluation_reason = DRAW_PT_PARENT_DEACTIVATED_REASON

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
