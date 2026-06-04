"""Builder component_trace predetto vs actual per fixture×strategia."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.backtest.v31_calibration_simulator_feature_engine import (
    FixtureSignals,
    extract_fixture_signals,
)
from app.services.backtest.v31_calibration_simulator_predictor import STRATEGY_REGISTRY
from app.services.backtest.v31_component_actual_registry import (
    BASE_KEYS_IN_MODEL,
    CONTEXT_MACRO_KEYS,
    MATCH_LEVEL_VARIABLES,
    MACRO_AREA_LABELS,
    get_variable_spec,
)
from app.services.backtest.v31_component_actual_resolver import resolve_actual_component_value
from app.services.backtest.v31_component_error_direction import (
    compute_error_direction,
    compute_suspicion_level,
    match_error_type,
    row_ui_status,
)


def _round4(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 4)


def _pct_delta(delta: float | None, predicted: float | None) -> float | None:
    if delta is None or predicted is None or abs(predicted) < 1e-6:
        return None
    return round(100.0 * float(delta) / float(predicted), 1)


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(float(w) for w in weights.values() if w > 0) or 1.0
    return {k: float(v) / total for k, v in weights.items() if v > 0}


def _build_input_row(
    db: Session,
    *,
    fixture_id: int,
    team_id: int,
    opponent_team_id: int,
    variable_key: str,
    predicted_value: float | None,
    weight: float | None,
    source: str,
    sample_size: int | None,
    fallback_used: bool,
    match_error: float | None,
    normalized_value: float | None = None,
    layer: str = "base",
    side: str = "home",
) -> dict[str, Any]:
    spec = get_variable_spec(variable_key)
    if spec is None:
        return {}

    resolved = resolve_actual_component_value(
        db,
        fixture_id=fixture_id,
        team_id=team_id,
        opponent_team_id=opponent_team_id,
        variable_key=variable_key,
        side=side,  # type: ignore[arg-type]
    )
    pred = _round4(predicted_value)
    act = _round4(resolved.value)
    delta = _round4((act - pred) if act is not None and pred is not None else None)
    w = float(weight) if weight is not None else 0.0

    if layer == "context" and pred is not None:
        pred_contrib = _round4(w * (float(pred) - 1.0))
        act_contrib = (
            _round4(w * (float(act) - 1.0))
            if act is not None and resolved.actual_comparison_type != "diagnostic_only"
            else None
        )
    else:
        pred_contrib = _round4(w * pred) if pred is not None else None
        act_contrib = _round4(w * act) if act is not None else None

    contrib_delta = (
        _round4(float(act_contrib) - float(pred_contrib))
        if act_contrib is not None and pred_contrib is not None
        else None
    )

    err_dir = compute_error_direction(
        match_error=match_error,
        predicted_value=pred,
        actual_value=act,
        delta=delta,
        comparison_type=resolved.actual_comparison_type,
    )
    suspicion = compute_suspicion_level(
        error_direction=err_dir,
        match_error=match_error,
        delta_pct=_pct_delta(delta, pred),
    )

    return {
        "key": variable_key,
        "label": spec.label,
        "macro_area": spec.macro_area,
        "macro_area_label": MACRO_AREA_LABELS.get(spec.macro_area, spec.macro_area),
        "predicted_value": pred,
        "actual_value": act,
        "delta": delta,
        "delta_pct": _pct_delta(delta, pred),
        "normalized_value": _round4(normalized_value if normalized_value is not None else pred),
        "weight": _round4(w),
        "weight_pct": _round4(w * 100.0),
        "predicted_contribution": pred_contrib,
        "actual_contribution_proxy": act_contrib,
        "contribution_delta": contrib_delta,
        "source": source,
        "actual_source": resolved.source,
        "status": "available" if pred is not None else "missing",
        "actual_status": resolved.status,
        "sample_size": sample_size,
        "fallback_used": fallback_used,
        "actual_comparison_type": resolved.actual_comparison_type,
        "error_direction": err_dir,
        "suspicion_level": suspicion,
        "ui_status": row_ui_status(err_dir, suspicion),
        "used_in_model": variable_key in BASE_KEYS_IN_MODEL or layer == "context",
    }


def _build_side_inputs(
    db: Session,
    *,
    fixture_id: int,
    team_id: int,
    opponent_team_id: int,
    team_name: str,
    side: str,
    side_signals: Any,
    base_trace: dict[str, Any],
    context_weights: dict[str, float],
    match_error: float | None,
) -> dict[str, Any]:
    components = base_trace.get("components") or {}
    weights_used = _normalize_weights(base_trace.get("base_weights_used") or {})
    sample_size = int((side_signals.team_raw or {}).get("sample_count") or 0)
    inputs: list[dict[str, Any]] = []

    for key in BASE_KEYS_IN_MODEL:
        if key not in weights_used:
            continue
        row = _build_input_row(
            db,
            fixture_id=fixture_id,
            team_id=team_id,
            opponent_team_id=opponent_team_id,
            variable_key=key,
            predicted_value=components.get(key),
            weight=weights_used.get(key),
            source=f"trace.components.{key}",
            sample_size=sample_size,
            fallback_used=False,
            match_error=match_error,
            layer="base",
            side=side,
        )
        if row:
            inputs.append(row)

    ctx_w = _normalize_weights(context_weights)
    for key in CONTEXT_MACRO_KEYS:
        if key not in ctx_w:
            continue
        macro_val = (side_signals.macros or {}).get(key)
        row = _build_input_row(
            db,
            fixture_id=fixture_id,
            team_id=team_id,
            opponent_team_id=opponent_team_id,
            variable_key=key,
            predicted_value=macro_val,
            weight=ctx_w.get(key),
            source=f"macro.{key}",
            sample_size=sample_size,
            fallback_used=False,
            match_error=match_error,
            normalized_value=macro_val,
            layer="context",
            side=side,
        )
        if row:
            inputs.append(row)

    return {
        "team_id": team_id,
        "team_name": team_name,
        "inputs": inputs,
    }


def _build_match_level_inputs(
    trace: dict[str, Any],
    match_error: float | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in MATCH_LEVEL_VARIABLES:
        key = spec.key
        val = trace.get(key)
        if key == "data_quality_score":
            dq = trace.get("data_quality") if isinstance(trace.get("data_quality"), dict) else {}
            val = dq.get("score") if dq else None
        if val is None and key not in trace:
            continue
        pred = _round4(float(val) if val is not None else None)
        err_dir = "not_comparable"
        out.append(
            {
                "key": key,
                "label": spec.label,
                "macro_area": spec.macro_area,
                "macro_area_label": MACRO_AREA_LABELS.get(spec.macro_area, spec.macro_area),
                "predicted_value": pred,
                "actual_value": None,
                "delta": None,
                "delta_pct": None,
                "normalized_value": pred,
                "weight": None,
                "weight_pct": None,
                "predicted_contribution": None,
                "actual_contribution_proxy": None,
                "contribution_delta": None,
                "source": spec.source,
                "actual_source": "n/a",
                "status": "available" if pred is not None else "missing",
                "actual_status": "diagnostic_only",
                "sample_size": None,
                "fallback_used": False,
                "actual_comparison_type": "diagnostic_only",
                "error_direction": err_dir,
                "suspicion_level": "low",
                "ui_status": "neutral",
                "used_in_model": True,
            },
        )
    return out


def build_component_comparison(
    db: Session,
    *,
    dataset_row: dict[str, Any],
    simulated_row: dict[str, Any],
    strategy_key: str,
) -> dict[str, Any] | None:
    """Costruisce payload completo per persistenza."""
    signals = extract_fixture_signals(dataset_row)
    if signals is None:
        return None

    meta = dataset_row.get("metadata") or {}
    trace = simulated_row.get("trace") if isinstance(simulated_row.get("trace"), dict) else {}
    spec = STRATEGY_REGISTRY.get(strategy_key)
    if spec is None:
        return None

    home_id = int(meta.get("home_team_id") or 0)
    away_id = int(meta.get("away_team_id") or 0)
    fixture_id = int(meta.get("fixture_id") or simulated_row.get("fixture_id") or 0)

    pred_total = simulated_row.get("predicted_total_sot")
    act_total = simulated_row.get("actual_total_sot")
    match_err = (
        float(act_total) - float(pred_total)
        if act_total is not None and pred_total is not None
        else simulated_row.get("error")
    )
    if match_err is not None:
        match_err = float(match_err)

    home_base_trace = trace.get("home_base_trace") or {}
    away_base_trace = trace.get("away_base_trace") or {}
    h_ctx_w = trace.get("home_context_weights") or {}
    a_ctx_w = trace.get("away_context_weights") or {}

    return {
        "match_summary": {
            "fixture_id": fixture_id,
            "round_number": int(meta.get("round_number") or simulated_row.get("round_number") or 0),
            "match": f"{meta.get('home_team_name')} vs {meta.get('away_team_name')}",
            "strategy_key": strategy_key,
            "predicted_total_sot": pred_total,
            "actual_total_sot": act_total,
            "predicted_home_sot": simulated_row.get("predicted_home_sot"),
            "predicted_away_sot": simulated_row.get("predicted_away_sot"),
            "error": match_err,
            "error_type": match_error_type(match_err),
        },
        "home": _build_side_inputs(
            db,
            fixture_id=fixture_id,
            team_id=home_id,
            opponent_team_id=away_id,
            team_name=str(meta.get("home_team_name") or "Casa"),
            side="home",
            side_signals=signals.home,
            base_trace=home_base_trace,
            context_weights=h_ctx_w,
            match_error=match_err,
        ),
        "away": _build_side_inputs(
            db,
            fixture_id=fixture_id,
            team_id=away_id,
            opponent_team_id=home_id,
            team_name=str(meta.get("away_team_name") or "Trasferta"),
            side="away",
            side_signals=signals.away,
            base_trace=away_base_trace,
            context_weights=a_ctx_w,
            match_error=match_err,
        ),
        "match_level": {"inputs": _build_match_level_inputs(trace, match_err)},
    }


def flatten_component_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Espande payload in righe tabella UI."""
    rows: list[dict[str, Any]] = []
    ms = payload.get("match_summary") or {}
    match_label = ms.get("match") or ""
    round_n = ms.get("round_number")
    strategy = ms.get("strategy_key")

    for side_key in ("home", "away"):
        side = payload.get(side_key) or {}
        team_name = side.get("team_name") or side_key
        for inp in side.get("inputs") or []:
            rows.append(
                {
                    **inp,
                    "match": match_label,
                    "round_number": round_n,
                    "fixture_id": ms.get("fixture_id"),
                    "strategy_key": strategy,
                    "team": team_name,
                    "team_side": side_key,
                    "layer": "team",
                },
            )

    for inp in (payload.get("match_level") or {}).get("inputs") or []:
        rows.append(
            {
                **inp,
                "match": match_label,
                "round_number": round_n,
                "fixture_id": ms.get("fixture_id"),
                "strategy_key": strategy,
                "team": "Match",
                "team_side": "match",
                "layer": "match",
            },
        )
    return rows
