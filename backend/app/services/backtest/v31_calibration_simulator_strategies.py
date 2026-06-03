"""Strategie predittive numeriche simulatore v3.1."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_buckets import bucket_label
from app.services.backtest.v31_calibration_simulator_cohort import CohortStats
from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_predictor import (
    STRATEGY_REGISTRY,
    predict_for_strategy,
)

STRATEGY_KEYS = tuple(STRATEGY_REGISTRY.keys())

STRATEGY_LABELS: dict[str, str] = {k: v.label for k, v in STRATEGY_REGISTRY.items()}

STRATEGY_DESCRIPTIONS: dict[str, str] = {k: v.description for k, v in STRATEGY_REGISTRY.items()}


def _pct_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values()) or 1.0
    return {k: round(100.0 * v / total, 1) for k, v in weights.items()}


def get_strategy_weights_payload(strategy_key: str) -> dict[str, Any]:
    spec = STRATEGY_REGISTRY[strategy_key]
    return {
        "strategy_key": strategy_key,
        "base_weights": spec.base_weights,
        "base_weights_pct": _pct_weights(spec.base_weights),
        "context_weights": spec.context_weights,
        "context_weights_pct": _pct_weights(spec.context_weights),
        "context_cap_min": spec.context_cap_min,
        "context_cap_max": spec.context_cap_max,
        "total_league_blend": spec.total_league_blend,
        "total_min": spec.total_min,
        "total_max": spec.total_max,
        "uses_dynamic_bias": spec.uses_dynamic_bias,
        "strategy_family": spec.strategy_family,
        "uses_dynamics": spec.uses_dynamics,
        "features_on": list(spec.base_weights.keys()),
        "macro_areas": list(spec.context_weights.keys()),
    }


def _base_row_fields(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata") or {}
    target = row.get("target") or {}
    return {
        "fixture_id": int(meta.get("fixture_id") or 0),
        "round_number": int(meta.get("round_number") or 0),
        "match": f"{meta.get('home_team_name') or 'Casa'} vs {meta.get('away_team_name') or 'Trasferta'}",
        "actual_total_sot": target.get("actual_total_sot"),
        "actual_home_sot": target.get("actual_home_sot"),
        "actual_away_sot": target.get("actual_away_sot"),
    }


def predict_row(
    row: dict[str, Any],
    strategy_key: str,
    *,
    bias_offset: float = 0.0,
    cohort: CohortStats | None = None,
) -> dict[str, Any]:
    """Predice sempre una riga (ok o failed); mai None."""
    base = _base_row_fields(row)
    base["strategy_key"] = strategy_key

    signals = extract_fixture_signals(row)
    if signals is None:
        return {
            **base,
            "prediction_status": "failed",
            "error_code": "V31_INVALID_FEATURES",
            "predicted_home_sot": None,
            "predicted_away_sot": None,
            "predicted_total_sot": None,
            "error": None,
            "abs_error": None,
            "coverage_outcome": None,
            "missing_fields": ["features"],
            "trace": {},
        }

    try:
        pred = predict_for_strategy(signals, strategy_key, bias_offset=bias_offset, cohort=cohort)
    except ValueError as exc:
        return {
            **base,
            "prediction_status": "failed",
            "error_code": "V31_UNKNOWN_STRATEGY",
            "predicted_home_sot": None,
            "predicted_away_sot": None,
            "predicted_total_sot": None,
            "error": None,
            "abs_error": None,
            "coverage_outcome": None,
            "missing_fields": signals.missing_fields,
            "trace": {"error": str(exc)},
        }

    total = pred.get("predicted_total_sot")
    if total is None:
        return {
            **base,
            "prediction_status": "failed",
            "error_code": "V31_MISSING_BASE_SOT",
            "predicted_home_sot": pred.get("predicted_home_sot"),
            "predicted_away_sot": pred.get("predicted_away_sot"),
            "predicted_total_sot": None,
            "error": None,
            "abs_error": None,
            "coverage_outcome": None,
            "missing_fields": pred.get("missing_fields") or signals.missing_fields,
            "trace": pred.get("trace") or {},
        }

    actual = base.get("actual_total_sot")
    error = None
    abs_error = None
    coverage_outcome = None
    if actual is not None:
        error = round(float(total) - float(actual), 4)
        abs_error = round(abs(error), 4)
        coverage_outcome = "win" if float(actual) > float(total) else "loss"

    trace = pred.get("trace") or {}
    trace["strategy_key"] = strategy_key
    trace["home_base_sot"] = pred.get("home_base_sot")
    trace["away_base_sot"] = pred.get("away_base_sot")
    trace["home_context_multiplier"] = pred.get("home_context_multiplier")
    trace["away_context_multiplier"] = pred.get("away_context_multiplier")

    pred_bucket = bucket_label(total)
    act_bucket = bucket_label(actual) if actual is not None else None

    return {
        **base,
        "prediction_status": "ok",
        "error_code": None,
        "predicted_home_sot": pred.get("predicted_home_sot"),
        "predicted_away_sot": pred.get("predicted_away_sot"),
        "predicted_total_sot": total,
        "predicted_bucket": pred_bucket,
        "actual_bucket": act_bucket,
        "error": error,
        "abs_error": abs_error,
        "coverage_outcome": coverage_outcome,
        "missing_fields": pred.get("missing_fields") or signals.missing_fields,
        "trace": trace,
    }


def predict_rows_for_strategy(
    rows: list[dict[str, Any]],
    strategy_key: str,
    *,
    cohort: CohortStats | None = None,
) -> list[dict[str, Any]]:
    """Predice tutte le righe; bias_corrected usa offset dinamico per round."""
    spec = STRATEGY_REGISTRY.get(strategy_key)
    if spec is None:
        return [predict_row(r, strategy_key, cohort=cohort) for r in rows]

    if not spec.uses_dynamic_bias:
        return [predict_row(r, strategy_key, cohort=cohort) for r in rows]

    indexed = list(enumerate(rows))
    indexed.sort(key=lambda x: int((x[1].get("metadata") or {}).get("round_number") or 0))
    bias_offset = 0.0
    n_prior = 0
    by_index: dict[int, dict[str, Any]] = {}
    for idx, row in indexed:
        out = predict_row(row, strategy_key, bias_offset=bias_offset, cohort=cohort)
        by_index[idx] = out
        if out.get("prediction_status") == "ok" and out.get("error") is not None:
            actual = out.get("actual_total_sot")
            pred = out.get("predicted_total_sot")
            if actual is not None and pred is not None:
                residual = float(actual) - float(pred)
                bias_offset = (bias_offset * n_prior + residual) / (n_prior + 1)
                n_prior += 1
    return [by_index[i] for i in range(len(rows))]


# Alias retrocompatibilità test legacy
simulate_row = predict_row
