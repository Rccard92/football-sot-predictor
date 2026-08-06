"""Sync idempotente segnali SI dalla matrice Cecchino (formula V3 + consenso)."""

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
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    FORMULA_SOURCE_PERSISTED_LIVE,
    LEGACY_SIGNAL_FORMULA_VERSION,
    REASON_DRAW_PT_PARENT_CONSENSUS_BELOW,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    consensus_by_group_from_matrix,
    inherit_draw_consensus,
    is_current_signal_matrix,
    normalize_formula_version,
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
from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import load_signal_min_book_odds
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


def _activation_pair_key(
    model_key: str,
    signal_group: str,
    source_column: str,
    *,
    formula_version: str = CURRENT_SIGNAL_FORMULA_VERSION,
) -> tuple[str, str, str, str]:
    return (model_key, normalize_formula_version(formula_version), signal_group, source_column)


def _empty_sync_counts() -> dict[str, int]:
    return {
        "created": 0,
        "updated": 0,
        "deactivated": 0,
        "skipped": 0,
        "skipped_non_current_formula_matrix": 0,
        "groups_consensus_passed": 0,
        "groups_consensus_rejected": 0,
        "single_formula_exempt_acquired": 0,
        "raw_si_cells": 0,
        "acquired_formula_cells": 0,
        "draw_pt_blocked_by_consensus": 0,
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


def _record_value_threshold_applied(
    counts: dict[str, int],
    target_market_key: str | None,
    *,
    min_book_odds: dict[str, Decimal] | None = None,
) -> None:
    if get_min_book_odd(target_market_key, min_book_odds=min_book_odds) is not None:
        counts["min_book_odd_threshold_applied"] += 1


def _record_deactivation_for_value_reason(counts: dict[str, int], value_reason: str) -> None:
    if value_reason == VALUE_REASON_BOOK_BELOW_MIN:
        counts["deactivated_min_book_odd"] += 1
    else:
        counts["deactivated_no_value"] += 1


def _apply_consensus_fields(
    activation: CecchinoSignalActivation,
    *,
    consensus: dict[str, Any],
    formula_version: str,
    formula_source_mode: str,
) -> None:
    activation.signal_formula_version = formula_version
    activation.consensus_policy_version = str(
        consensus.get("consensus_policy_version") or SIGNAL_CONSENSUS_POLICY_VERSION,
    )
    activation.formula_source_mode = formula_source_mode
    activation.consensus_source_group = consensus.get("consensus_source_group")
    activation.consensus_eligible = bool(consensus.get("consensus_eligible"))
    activation.consensus_available_count = int(consensus.get("consensus_available_count") or 0)
    activation.consensus_required_count = int(consensus.get("consensus_required_count") or 0)
    activation.consensus_yes_count = int(consensus.get("consensus_yes_count") or 0)
    activation.consensus_yes_columns_json = list(consensus.get("consensus_yes_columns") or [])
    activation.consensus_passed = bool(consensus.get("consensus_passed"))
    activation.is_acquired = bool(consensus.get("is_acquired"))
    activation.acquisition_status = str(consensus.get("acquisition_status") or "")


def _deactivate_draw_pair(
    *,
    mk: str,
    source_column: str,
    formula_version: str,
    by_key: dict[tuple[str, str, str, str], CecchinoSignalActivation],
    counts: dict[str, int],
    reason: str,
    now: datetime,
) -> None:
    deactivation_reason = deactivation_reason_for_value_gate(reason)
    for signal_group in ("DRAW", "DRAW_PT"):
        activation = by_key.get(_activation_pair_key(mk, signal_group, source_column, formula_version=formula_version))
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
    by_key: dict[tuple[str, str, str, str], CecchinoSignalActivation],
    db: Session,
    counts: dict[str, int],
    consensus: dict[str, Any],
    formula_version: str,
    formula_source_mode: str,
    include_odds: bool = True,
    derived_reason: str | None = None,
) -> CecchinoSignalActivation:
    key = _activation_pair_key(
        mk,
        cell["signal_group"],
        cell["source_column"],
        formula_version=formula_version,
    )
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

    _apply_consensus_fields(
        activation,
        consensus=consensus,
        formula_version=formula_version,
        formula_source_mode=formula_source_mode,
    )
    if consensus.get("is_acquired"):
        counts["acquired_formula_cells"] += 1
    return activation


def _sync_draw_pt_derived(
    *,
    row: CecchinoTodayFixture,
    mk: str,
    meta: dict[str, object],
    cell: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    inputs: dict[str, Any],
    by_key: dict[tuple[str, str, str, str], CecchinoSignalActivation],
    db: Session,
    counts: dict[str, int],
    active_keys: set[tuple[str, str, str, str]],
    match_result: dict[str, Any],
    min_book_odds: dict[str, Decimal],
    draw_consensus: dict[str, Any],
    formula_version: str,
    formula_source_mode: str,
) -> None:
    pt_consensus = inherit_draw_consensus(draw_consensus)
    pt_key = _activation_pair_key(mk, "DRAW_PT", cell["source_column"], formula_version=formula_version)
    existing_pt = by_key.get(pt_key)

    if not draw_consensus.get("consensus_passed"):
        counts["draw_pt_blocked_by_consensus"] += 1
        if existing_pt is not None and existing_pt.is_current:
            _deactivate_activation(
                existing_pt,
                reason=REASON_DRAW_PT_PARENT_CONSENSUS_BELOW,
                now=datetime.now(timezone.utc),
            )
            counts["draw_pt_deactivated"] += 1
            counts["derived_observations_deactivated"] += 1
        return

    pt_kpi_ctx = resolve_kpi_odds_for_activation(
        kpi_panel,
        signal_group="DRAW_PT",
        target_market_key=SEL_DRAW_PT,
    )
    pt_passed, pt_reason, pt_value_meta = signal_has_value_from_kpi_context(
        pt_kpi_ctx,
        target_market_key=SEL_DRAW_PT,
        min_book_odds=min_book_odds,
    )
    _record_value_threshold_applied(counts, SEL_DRAW_PT, min_book_odds=min_book_odds)

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
        consensus=pt_consensus,
        formula_version=formula_version,
        formula_source_mode=formula_source_mode,
        include_odds=True,
        derived_reason=derived_reason,
    )
    if pt_activation.target_market_key:
        eval_result = evaluate_signal_activation(pt_activation, match_result)
        apply_evaluation_to_activation(pt_activation, eval_result, result_status=row.match_display_status)
        if eval_result["evaluation_status"] in ("won", "lost"):
            counts["draw_pt_evaluated"] = counts.get("draw_pt_evaluated", 0) + 1


def _iter_si_cells(
    signals_matrix: dict[str, Any],
    *,
    consensus_by_group: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = signals_matrix.get("rows") or []
    if not isinstance(rows, list):
        return []
    group_consensus = consensus_by_group or consensus_by_group_from_matrix(signals_matrix)
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
        consensus = group_consensus.get(signal_group) or row.get("consensus") or {}
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
                    "consensus": consensus,
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
    min_book_odds: dict[str, Decimal] | None = None,
    formula_source_mode: str = FORMULA_SOURCE_PERSISTED_LIVE,
    formula_version: str | None = None,
) -> dict[str, int]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {**_empty_sync_counts(), "skipped": 1}

    if min_book_odds is None:
        min_book_odds = load_signal_min_book_odds(db)

    mk = str(model_key).upper()
    meta = model_meta or model_meta_for_key(mk)

    output = row.cecchino_output_json or {}
    if signals_matrix is None:
        signals_matrix = output.get("signals_matrix") if isinstance(output, dict) else None
    if not isinstance(signals_matrix, dict) or signals_matrix.get("status") != STATUS_AVAILABLE:
        return {**_empty_sync_counts(), "skipped": 1}

    # Current-only: rifiuta matrici senza formula_version, V1, V2 o sconosciute.
    # Non rinomina e non forza CURRENT su risultati legacy.
    # Reason code: signal_matrix_formula_version_not_current
    if not is_current_signal_matrix(signals_matrix):
        counts = _empty_sync_counts()
        counts["skipped"] = 1
        counts["skipped_non_current_formula_matrix"] = 1
        return counts

    # Arg esplicito deve essere coerente con V3; altrimenti ignora (matrice già validata).
    if formula_version is not None:
        explicit = str(formula_version).strip()
        if explicit and explicit != CURRENT_SIGNAL_FORMULA_VERSION and explicit not in ("current", "v3"):
            counts = _empty_sync_counts()
            counts["skipped"] = 1
            counts["skipped_non_current_formula_matrix"] = 1
            return counts

    fv = CURRENT_SIGNAL_FORMULA_VERSION

    kpi_panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    inputs = signals_matrix.get("inputs") or {}
    consensus_by_group = consensus_by_group_from_matrix(signals_matrix)
    si_cells = _iter_si_cells(signals_matrix, consensus_by_group=consensus_by_group)
    active_keys: set[tuple[str, str, str, str]] = set()

    # Solo activation V3 della formula corrente (non tocca V1/V2)
    existing = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.today_fixture_id == int(today_fixture_id),
                CecchinoSignalActivation.model_key == mk,
                CecchinoSignalActivation.signal_formula_version == fv,
            ),
        ).all(),
    )
    by_key: dict[tuple[str, str, str, str], CecchinoSignalActivation] = {}
    for activation in existing:
        by_key[
            _activation_pair_key(
                activation.model_key,
                activation.signal_group,
                activation.source_column,
                formula_version=fv,
            )
        ] = activation

    counts = _empty_sync_counts()
    counts["raw_si_cells"] = len(si_cells)
    match_result = match_result_from_fixture(row)
    now = datetime.now(timezone.utc)

    tracked_groups: set[str] = set()
    for group, consensus in consensus_by_group.items():
        if consensus.get("consensus_yes_count", 0) <= 0:
            continue
        if group in tracked_groups:
            continue
        tracked_groups.add(group)
        if consensus.get("acquisition_status") == "acquired_single_formula_exempt":
            counts["single_formula_exempt_acquired"] += 1
        elif consensus.get("consensus_passed"):
            counts["groups_consensus_passed"] += 1
        else:
            counts["groups_consensus_rejected"] += 1

    for cell in si_cells:
        counts["si_cells_seen"] += 1
        consensus = cell.get("consensus") or consensus_by_group.get(cell["signal_group"]) or {}
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
            min_book_odds=min_book_odds,
        )
        _record_value_threshold_applied(counts, target_market_key, min_book_odds=min_book_odds)
        key = _activation_pair_key(
            mk,
            cell["signal_group"],
            cell["source_column"],
            formula_version=fv,
        )

        if cell["signal_group"] == "DRAW":
            if not passed:
                _record_no_value_skip(counts, value_reason)
                _deactivate_draw_pair(
                    mk=mk,
                    source_column=cell["source_column"],
                    formula_version=fv,
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
                consensus=consensus,
                formula_version=fv,
                formula_source_mode=formula_source_mode,
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
                min_book_odds=min_book_odds,
                draw_consensus=consensus,
                formula_version=fv,
                formula_source_mode=formula_source_mode,
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
            consensus=consensus,
            formula_version=fv,
            formula_source_mode=formula_source_mode,
        )
        if activation.target_market_key:
            eval_result = evaluate_signal_activation(activation, match_result)
            apply_evaluation_to_activation(activation, eval_result, result_status=row.match_display_status)

    for activation in existing:
        key = _activation_pair_key(
            activation.model_key,
            activation.signal_group,
            activation.source_column,
            formula_version=fv,
        )
        if key not in active_keys and activation.is_current:
            activation.is_current = False
            activation.deactivated_at = now
            counts["deactivated"] += 1
            if activation.signal_group == "DRAW_PT":
                counts["draw_pt_deactivated"] += 1
                counts["derived_observations_deactivated"] += 1
                # Prefer consensus reason if parent DRAW lacks consensus
                draw_c = consensus_by_group.get("DRAW") or {}
                if not draw_c.get("consensus_passed"):
                    activation.evaluation_reason = REASON_DRAW_PT_PARENT_CONSENSUS_BELOW
                else:
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


# Re-export for tests / callers
__all__ = [
    "sync_cecchino_signal_activations",
    "remap_legacy_scala_activations_in_range",
    "_iter_si_cells",
    "_activation_pair_key",
    "CURRENT_SIGNAL_FORMULA_VERSION",
    "LEGACY_SIGNAL_FORMULA_VERSION",
]
