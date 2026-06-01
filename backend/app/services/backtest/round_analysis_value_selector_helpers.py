"""Helper condivisi per value selector v3.0 (simulazione read-only)."""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_diagnostics_aggregator import compute_low_total_risk_score
from app.services.backtest.round_analysis_mode_stats import is_advised_label
from app.services.backtest.round_analysis_v21_trace_helpers import V21_MACRO_AVG_KEYS
from app.services.backtest.sot_pick_evaluation_logic import compute_pick_outcome

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def block_cautious_gioca(block: dict[str, Any] | None) -> bool:
    if not isinstance(block, dict):
        return False
    return is_advised_label(str(block.get("cautious_advice") or ""))


def cautious_line(block: dict[str, Any] | None) -> float | None:
    if not isinstance(block, dict):
        return None
    ln = block.get("cautious_line")
    return float(ln) if ln is not None else None


def outcome_for_line(actual: int, line: float) -> str:
    return "WIN" if compute_pick_outcome(line, actual) == "win" else "LOSS"


def pick_from_block(
    fx: dict[str, Any],
    block: dict[str, Any],
    *,
    model_key: str,
    line: float | None = None,
) -> dict[str, Any] | None:
    if line is None:
        line = cautious_line(block)
    if line is None:
        return None
    actual = int(fx["actual_total_sot"])
    outcome = outcome_for_line(actual, float(line))
    pt = block.get("predicted_total_sot")
    return {
        "analysis_id": fx["analysis_id"],
        "round_number": fx["round_number"],
        "fixture_id": fx["fixture_id"],
        "match": fx["match"],
        "actual_total_sot": actual,
        "predicted_total_sot": float(pt) if pt is not None else None,
        "line": float(line),
        "outcome": outcome,
        "model_key": model_key,
        "mode": "cautious",
    }


def _round4(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 4)


def _predicted(block: dict[str, Any] | None) -> float | None:
    if not isinstance(block, dict):
        return None
    pt = block.get("predicted_total_sot")
    return float(pt) if pt is not None else None


def fixture_context(fx: dict[str, Any]) -> dict[str, Any]:
    v11_block = (fx.get("models") or {}).get(V11) or {}
    v21_block = (fx.get("models") or {}).get(V21) or {}
    v11_pt = _predicted(v11_block)
    v21_pt = _predicted(v21_block)
    gap = None
    if v11_pt is not None and v21_pt is not None:
        gap = _round4(v21_pt - v11_pt)
    warnings = list(v21_block.get("warnings") or [])
    return {
        "v11_block": v11_block,
        "v21_block": v21_block,
        "v11_predicted_total": v11_pt,
        "v21_predicted_total": v21_pt,
        "prediction_gap": gap,
        "macros": dict(fx.get("v21_macros") or {}),
        "warning_count": len(warnings),
        "warnings": warnings,
        "split_status": fx.get("split_status") or "missing",
        "confidence": str(v21_block.get("confidence") or ""),
        "sample_bucket": v21_block.get("sample_bucket"),
        "low_total_risk_v2_score": fx.get("low_total_risk_v2_score"),
        "low_total_risk_v2_bucket": fx.get("low_total_risk_v2_bucket"),
    }


def build_v21_trace_summary(explanation_v21: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(explanation_v21, dict):
        return {"fallback_count": None, "macro_statuses": {}}
    statuses: dict[str, str] = {}
    for side_key in ("home", "away"):
        side = explanation_v21.get(side_key)
        if not isinstance(side, dict):
            continue
        for macro in side.get("macros") or []:
            if isinstance(macro, dict) and macro.get("key"):
                statuses[f"{side_key}_{macro['key']}"] = str(macro.get("status") or "")
    return {
        "fallback_count": explanation_v21.get("fallback_count"),
        "leakage_guard": explanation_v21.get("leakage_guard"),
        "macro_statuses": statuses,
    }


def enrich_pick(
    fx: dict[str, Any],
    pick: dict[str, Any],
    strategy_id: str,
    **extra: Any,
) -> dict[str, Any]:
    ctx = fixture_context(fx)
    out = dict(pick)
    out["strategy_id"] = strategy_id
    out["v1_1_predicted_total"] = ctx["v11_predicted_total"]
    out["v2_1_predicted_total"] = ctx["v21_predicted_total"]
    out["prediction_gap_v21_minus_v11"] = ctx["prediction_gap"]
    out["low_total_risk_v2_score"] = ctx["low_total_risk_v2_score"]
    out["low_total_risk_v2_bucket"] = ctx["low_total_risk_v2_bucket"]
    out.update(extra)
    return out


def build_loss_diagnostic(fx: dict[str, Any], pick: dict[str, Any], strategy_id: str) -> dict[str, Any]:
    ctx = fixture_context(fx)
    v21_block = ctx["v21_block"]
    macros = ctx["macros"]
    expl = fx.get("explanation_v21")
    risk_row = {
        "block": v21_block,
        "explanation_v21": expl,
    }
    risk_v1 = compute_low_total_risk_score(risk_row)
    macro_out = {k: macros.get(k) for k in V21_MACRO_AVG_KEYS}
    return {
        "round_number": pick.get("round_number"),
        "fixture_id": pick.get("fixture_id"),
        "match": pick.get("match"),
        "actual_total_sot": pick.get("actual_total_sot"),
        "predicted_total_sot": pick.get("predicted_total_sot"),
        "line": pick.get("line"),
        "selected_line": pick.get("selected_line", pick.get("line")),
        "strategy_id": strategy_id,
        "outcome": pick.get("outcome"),
        "model_key": pick.get("model_key"),
        "mode": pick.get("mode", "cautious"),
        "v1_1_predicted_total": ctx["v11_predicted_total"],
        "v2_1_predicted_total": ctx["v21_predicted_total"],
        "prediction_gap_v21_minus_v11": ctx["prediction_gap"],
        "v21_trace_summary": build_v21_trace_summary(expl),
        "v21_macros": macro_out,
        "fallback_count": (expl or {}).get("fallback_count") if isinstance(expl, dict) else None,
        "warnings": ctx["warnings"],
        "confidence": ctx["confidence"],
        "sample_bucket": ctx["sample_bucket"],
        "low_total_risk_score": risk_v1,
        "low_total_risk_v2_score": ctx["low_total_risk_v2_score"],
        "low_total_risk_v2_bucket": ctx["low_total_risk_v2_bucket"],
        "confidence_tier": pick.get("confidence_tier"),
        "reason_codes": pick.get("reason_codes"),
    }


def compute_strategy_verdict(picks: int, hit_rate: float | None) -> str:
    if hit_rate is None or picks <= 0:
        return "neutral"
    hr = float(hit_rate)
    if hr >= 72 and picks >= 80:
        return "excellent"
    if hr >= 70 and picks >= 60:
        return "promising"
    if hr >= 68 and picks >= 120:
        return "balanced"
    if hr >= 72 and picks < 60:
        return "too_selective"
    if hr < 66:
        return "weak"
    return "neutral"
