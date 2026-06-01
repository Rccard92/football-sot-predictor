"""Strategie value selector v3.0-C (simulazione read-only)."""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_value_selector_helpers import (
    V11,
    V21,
    block_cautious_gioca,
    cautious_line,
    enrich_pick,
    fixture_context,
    pick_from_block,
)

V3_STRATEGY_LABELS: dict[str, str] = {
    "v3_safe_6_5_strict": "v3 safe 6.5 strict",
    "v3_safe_6_5_balanced": "v3 safe 6.5 balanced",
    "v3_consensus_balanced_min_line": "v3 consensus balanced (min line)",
    "v3_premium_7_5_only": "v3 premium 7.5 only",
    "v3_hybrid_value_selector": "v3 hybrid value selector",
}

V3_STRATEGY_IDS = tuple(V3_STRATEGY_LABELS.keys())

_hybrid_no_bet_audit: list[dict[str, Any]] = []


def get_hybrid_no_bet_audit() -> list[dict[str, Any]]:
    return list(_hybrid_no_bet_audit)


def _macro_gt(macros: dict[str, Any], key: str, threshold: float) -> bool:
    v = macros.get(key)
    return v is not None and float(v) > threshold


def _macro_lt(macros: dict[str, Any], key: str, threshold: float) -> bool:
    v = macros.get(key)
    return v is not None and float(v) < threshold


def _passes_65_strict(fx: dict[str, Any], ctx: dict[str, Any]) -> tuple[bool, str | None]:
    v21 = ctx["v21_block"]
    if not block_cautious_gioca(v21):
        return False, "v21_not_gioca"
    ln = cautious_line(v21)
    if ln is None or float(ln) != 6.5:
        return False, "not_line_65"
    pt = ctx["v21_predicted_total"]
    if pt is None or not (7.50 <= float(pt) <= 8.25):
        return False, "pred_out_of_range"
    macros = ctx["macros"]
    if _macro_gt(macros, "weighted_macro_multiplier_avg", 1.10):
        return False, "wmm_too_high"
    cq, pace = macros.get("chance_quality_avg"), macros.get("pace_control_avg")
    if cq is not None and pace is not None and float(cq) > 1.12 and float(pace) > 1.08:
        return False, "chance_pace_overheat"
    if ctx["warning_count"] >= 4:
        return False, "too_many_warnings"
    if ctx["confidence"].lower() == "low":
        return False, "confidence_low"
    if ctx["sample_bucket"] == "early_low_sample":
        return False, "early_low_sample"
    if _macro_lt(macros, "injuries_unavailable_avg", 0.88):
        return False, "injuries_low"
    if _macro_lt(macros, "lineups_avg", 0.95):
        return False, "lineups_low"
    return True, None


def _passes_65_balanced(fx: dict[str, Any], ctx: dict[str, Any]) -> tuple[bool, str | None]:
    v21 = ctx["v21_block"]
    if not block_cautious_gioca(v21):
        return False, "v21_not_gioca"
    ln = cautious_line(v21)
    if ln is None or float(ln) != 6.5:
        return False, "not_line_65"
    pt = ctx["v21_predicted_total"]
    if pt is None or not (7.40 <= float(pt) <= 8.40):
        return False, "pred_out_of_range"
    macros = ctx["macros"]
    if _macro_gt(macros, "weighted_macro_multiplier_avg", 1.15):
        return False, "wmm_too_high"
    cq, pace = macros.get("chance_quality_avg"), macros.get("pace_control_avg")
    if cq is not None and pace is not None and float(cq) > 1.15 and float(pace) > 1.12:
        return False, "chance_pace_overheat"
    if ctx["warning_count"] >= 5:
        return False, "too_many_warnings"
    if ctx["confidence"].lower() == "low":
        return False, "confidence_low"
    unav, pl = macros.get("injuries_unavailable_avg"), macros.get("player_layer_avg")
    if unav is not None and pl is not None and float(unav) < 0.85 and float(pl) < 1.00:
        return False, "injuries_player_weak"
    return True, None


def _passes_75_premium(fx: dict[str, Any], ctx: dict[str, Any]) -> tuple[bool, str | None]:
    v11, v21 = ctx["v11_block"], ctx["v21_block"]
    if not block_cautious_gioca(v11) or not block_cautious_gioca(v21):
        return False, "consensus_required"
    ln = cautious_line(v21)
    if ln is None or float(ln) != 7.5:
        return False, "not_line_75"
    v21_pt, v11_pt = ctx["v21_predicted_total"], ctx["v11_predicted_total"]
    if v21_pt is None or float(v21_pt) < 8.50:
        return False, "v21_pred_low"
    if v11_pt is None or float(v11_pt) < 7.80:
        return False, "v11_pred_low"
    macros = ctx["macros"]
    wmm = macros.get("weighted_macro_multiplier_avg")
    if wmm is None or not (0.95 <= float(wmm) <= 1.08):
        return False, "wmm_out_of_premium_band"
    if _macro_gt(macros, "chance_quality_avg", 1.12):
        return False, "chance_quality_high"
    if _macro_gt(macros, "pace_control_avg", 1.10):
        return False, "pace_high"
    if _macro_gt(macros, "offensive_production_avg", 1.15):
        return False, "offensive_high"
    if _macro_lt(macros, "lineups_avg", 0.98):
        return False, "lineups_low"
    if _macro_lt(macros, "injuries_unavailable_avg", 0.90):
        return False, "injuries_low"
    if ctx["warning_count"] > 3:
        return False, "too_many_warnings"
    if ctx["confidence"].lower() == "low":
        return False, "confidence_low"
    return True, None


def strategy_v3_safe_65_strict(fx: dict[str, Any]) -> dict[str, Any] | None:
    ctx = fixture_context(fx)
    ok, _ = _passes_65_strict(fx, ctx)
    if not ok:
        return None
    pick = pick_from_block(fx, ctx["v21_block"], model_key=V21, line=6.5)
    return enrich_pick(fx, pick, "v3_safe_6_5_strict") if pick else None


def strategy_v3_safe_65_balanced(fx: dict[str, Any]) -> dict[str, Any] | None:
    ctx = fixture_context(fx)
    ok, _ = _passes_65_balanced(fx, ctx)
    if not ok:
        return None
    pick = pick_from_block(fx, ctx["v21_block"], model_key=V21, line=6.5)
    return enrich_pick(fx, pick, "v3_safe_6_5_balanced") if pick else None


def strategy_v3_consensus_balanced_min_line(fx: dict[str, Any]) -> dict[str, Any] | None:
    ctx = fixture_context(fx)
    v11, v21 = ctx["v11_block"], ctx["v21_block"]
    if not block_cautious_gioca(v11) or not block_cautious_gioca(v21):
        return None
    ln11, ln21 = cautious_line(v11), cautious_line(v21)
    if ln11 is None or ln21 is None:
        return None
    line = min(float(ln11), float(ln21))
    if line not in (5.5, 6.5, 7.5):
        return None
    v21_pt = ctx["v21_predicted_total"]
    if line == 5.5 and (v21_pt is None or float(v21_pt) < 7.20):
        return None
    if line == 7.5:
        if v21_pt is None or float(v21_pt) < 8.35:
            return None
        macros = ctx["macros"]
        if _macro_gt(macros, "weighted_macro_multiplier_avg", 1.12):
            return None
        if _macro_gt(macros, "chance_quality_avg", 1.15):
            return None
    gap = ctx["prediction_gap"]
    if gap is not None and abs(float(gap)) > 1.25:
        return None
    if ctx["warning_count"] >= 5:
        return None
    pick = pick_from_block(fx, v21, model_key=V21, line=line)
    return enrich_pick(fx, pick, "v3_consensus_balanced_min_line", selected_line=line) if pick else None


def strategy_v3_premium_75_only(fx: dict[str, Any]) -> dict[str, Any] | None:
    ctx = fixture_context(fx)
    ok, _ = _passes_75_premium(fx, ctx)
    if not ok:
        return None
    pick = pick_from_block(fx, ctx["v21_block"], model_key=V21, line=7.5)
    return enrich_pick(fx, pick, "v3_premium_7_5_only", selected_line=7.5) if pick else None


def strategy_v3_hybrid_value_selector(fx: dict[str, Any]) -> dict[str, Any] | None:
    ctx = fixture_context(fx)
    v21 = ctx["v21_block"]
    if not block_cautious_gioca(v21):
        return None
    ln = cautious_line(v21)
    if ln is None or float(ln) >= 8.5 or float(ln) == 5.5:
        _hybrid_no_bet_audit.append(
            {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": "line_excluded"},
        )
        return None
    if ctx["low_total_risk_v2_bucket"] == "high":
        _hybrid_no_bet_audit.append(
            {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": "low_total_risk_v2_high"},
        )
        return None
    gap = ctx["prediction_gap"]
    if gap is not None and float(gap) > 1.30:
        _hybrid_no_bet_audit.append(
            {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": "v21_v11_gap_too_high"},
        )
        return None
    macros = ctx["macros"]
    if _macro_gt(macros, "weighted_macro_multiplier_avg", 1.15):
        _hybrid_no_bet_audit.append(
            {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": "wmm_overheat"},
        )
        return None

    reason_codes: list[str] = []
    tier = "weak"
    v11_gioca = block_cautious_gioca(ctx["v11_block"])
    ln11 = cautious_line(ctx["v11_block"])
    consensus_65 = (
        v11_gioca
        and ln11 is not None
        and ln is not None
        and float(ln) == 6.5
        and min(float(ln11), float(ln)) == 6.5
    )

    if float(ln) == 6.5:
        ok, reason = _passes_65_balanced(fx, ctx)
        if not ok:
            _hybrid_no_bet_audit.append(
                {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": reason or "65_filters_fail"},
            )
            return None
        reason_codes.append("line_65_balanced")
        if consensus_65:
            tier = "strong"
            reason_codes.append("consensus_strong")
        elif not v11_gioca:
            tier = "medium"
            reason_codes.append("v21_only_medium")
        else:
            tier = "weak"
    elif float(ln) == 7.5:
        ok, reason = _passes_75_premium(fx, ctx)
        if not ok:
            _hybrid_no_bet_audit.append(
                {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": reason or "75_premium_fail"},
            )
            return None
        reason_codes.append("line_75_premium")
        tier = "strong" if v11_gioca else "medium"
    else:
        _hybrid_no_bet_audit.append(
            {"fixture_id": fx["fixture_id"], "match": fx["match"], "no_bet_reason": "unsupported_line"},
        )
        return None

    pick = pick_from_block(fx, v21, model_key=V21, line=float(ln))
    if not pick:
        return None
    return enrich_pick(
        fx,
        pick,
        "v3_hybrid_value_selector",
        selected_line=float(ln),
        confidence_tier=tier,
        reason_codes=reason_codes,
    )


def reset_hybrid_audit() -> None:
    global _hybrid_no_bet_audit
    _hybrid_no_bet_audit = []


V3_STRATEGY_FN = {
    "v3_safe_6_5_strict": strategy_v3_safe_65_strict,
    "v3_safe_6_5_balanced": strategy_v3_safe_65_balanced,
    "v3_consensus_balanced_min_line": strategy_v3_consensus_balanced_min_line,
    "v3_premium_7_5_only": strategy_v3_premium_75_only,
    "v3_hybrid_value_selector": strategy_v3_hybrid_value_selector,
}
