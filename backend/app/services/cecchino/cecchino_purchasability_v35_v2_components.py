"""Componenti V / D / R / Value Core / Acquisition / S multi-block / Q2 — Structural V2."""

from __future__ import annotations

import math
from typing import Any

from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    clip_prob,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    D_SCALE_V2,
    PROB_EPSILON,
    Q_BOOK_FALLBACK_PENALTY,
    Q_DERIVED_FAIR_PENALTY,
    Q_EXTREME_DIVERGENCE_MAX_PENALTY,
    Q_EXTREME_DIVERGENCE_RANGE,
    Q_EXTREME_DIVERGENCE_START,
    Q_OVERROUND_BASE,
    Q_OVERROUND_MAX_PENALTY,
    Q_OVERROUND_RANGE,
    QUALITY_FACTOR_BASE,
    S_SUPPORT_SCALE_V2,
    STRUCTURAL_FACTOR_BASE,
    STRUCTURAL_FACTOR_MISSING,
    V_SCALE_V2,
    VALUE_CORE_D_WEIGHT,
    VALUE_CORE_V_WEIGHT,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_relations import (
    StructuralEvidenceBlock,
    blocks_for_market,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_utils import clamp_v2


def logit(p: float, *, epsilon: float = PROB_EPSILON) -> float:
    clipped = clip_prob(p, eps=epsilon)
    return math.log(clipped / (1.0 - clipped))


def delta_logit(p_model: float, p_fair: float) -> float:
    return logit(p_model) - logit(p_fair)


def is_valid_open_probability(p: float | None) -> bool:
    if p is None:
        return False
    return 0.0 < float(p) < 1.0


def compute_executable_value_v2(expected_value: float) -> dict[str, Any]:
    """V = 100 × (1 - exp(-EV / 0.60)), clamp 0–100."""
    if expected_value <= 0:
        score = 0.0
    else:
        score = 100.0 * (1.0 - math.exp(-expected_value / V_SCALE_V2))
    score = clamp_v2(score, 0.0, 100.0)
    return {
        "component": "executable_value",
        "expected_value": expected_value,
        "score": score,
        "scale": V_SCALE_V2,
        "formula": "100 * (1 - exp(-EV / scale))",
        "status": "available",
    }


def compute_market_disagreement_v2(
    probability_cecchino: float,
    fair_book_probability: float,
) -> dict[str, Any]:
    """D = 100 × (1 - exp(-delta_logit / 0.85)) for delta > 0."""
    dl = delta_logit(probability_cecchino, fair_book_probability)
    if dl <= 0:
        d_score = 0.0
    else:
        d_score = 100.0 * (1.0 - math.exp(-dl / D_SCALE_V2))
    d_score = clamp_v2(d_score, 0.0, 100.0)
    return {
        "component": "market_disagreement",
        "delta_logit": dl,
        "score": d_score,
        "scale": D_SCALE_V2,
        "formula": "100 * (1 - exp(-delta_logit / scale))",
        "status": "available",
    }


def compute_value_core(v_score: float, d_score: float) -> dict[str, Any]:
    value_core = VALUE_CORE_V_WEIGHT * v_score + VALUE_CORE_D_WEIGHT * d_score
    return {
        "value_core": value_core,
        "V_contribution": VALUE_CORE_V_WEIGHT * v_score,
        "D_contribution": VALUE_CORE_D_WEIGHT * d_score,
        "V_weight": VALUE_CORE_V_WEIGHT,
        "D_weight": VALUE_CORE_D_WEIGHT,
    }


def compute_base_rate_reliability(
    probability_cecchino: float,
    fair_book_probability: float,
) -> dict[str, Any]:
    """Base-rate Reliability — geometric mean; NOT a calibrated win probability."""
    reliability_probability = math.sqrt(
        float(probability_cecchino) * float(fair_book_probability)
    )
    r_score = clamp_v2(100.0 * reliability_probability, 0.0, 100.0)
    return {
        "component": "base_rate_reliability",
        "label": "Base-rate Reliability",
        "reliability_probability": reliability_probability,
        "score": r_score,
        "R": r_score,
        "is_calibrated_probability": False,
        "is_win_probability": False,
        "formula": "R = 100 * sqrt(p_cecchino * p_fair)",
        "status": "available",
    }


def compute_acquisition_core(value_core: float, r_score: float) -> dict[str, Any]:
    acquisition_core = math.sqrt(max(value_core, 0.0) * max(r_score, 0.0))
    return {
        "value_core": value_core,
        "R": r_score,
        "acquisition_core": acquisition_core,
        "formula": "sqrt(value_core * R)",
    }


def _support_from_delta(delta: float, *, inverted: bool) -> float:
    signed = -delta if inverted else delta
    return clamp_v2(
        50.0 + 50.0 * math.tanh(signed / S_SUPPORT_SCALE_V2),
        0.0,
        100.0,
    )


def _resolve_probs_for_market(
    market_key: str,
    *,
    probs_by_market: dict[str, dict[str, float | None]],
) -> tuple[float | None, float | None]:
    entry = probs_by_market.get(market_key) or {}
    p_cec = entry.get("probability_cecchino")
    p_fair = entry.get("fair_book_probability")
    if not is_valid_open_probability(p_cec) or not is_valid_open_probability(p_fair):
        return None, None
    return float(p_cec), float(p_fair)


def _evaluate_block(
    block: StructuralEvidenceBlock,
    *,
    probs_by_market: dict[str, dict[str, float | None]],
) -> dict[str, Any]:
    configured = len(block.related_markets)
    opponent_details: list[dict[str, Any]] = []
    supports: list[float] = []

    for related_mk in block.related_markets:
        p_cec, p_fair = _resolve_probs_for_market(
            related_mk, probs_by_market=probs_by_market
        )
        detail: dict[str, Any] = {
            "selected_market": block.selected_market,
            "related_market": related_mk,
            "relation_type": (
                "same_family_opposition_support"
                if block.block_type == "same_family_opposition"
                else block.block_type
            ),
            "opponent_delta_logit": None,
            "support_score": None,
            "relation_strength": block.configured_strength,
            "data_available": False,
            "used_in_score": True,
            "reason": block.reason,
        }
        if p_cec is not None and p_fair is not None:
            od = delta_logit(p_cec, p_fair)
            support = _support_from_delta(
                od, inverted=(block.support_mode == "opposition_inverted")
            )
            detail["opponent_delta_logit"] = od
            detail["support_score"] = support
            detail["data_available"] = True
            supports.append(support)
        opponent_details.append(detail)

    available = len(supports)
    coverage = (available / configured) if configured > 0 else 0.0
    block_confidence = block.configured_strength * coverage
    block_raw = (
        sum(supports) / available if available > 0 else None
    )

    return {
        "block_type": block.block_type,
        "selected_market": block.selected_market,
        "related_markets": list(block.related_markets),
        "configured_strength": block.configured_strength,
        "configured_opponents": configured,
        "available_opponents": available,
        "coverage": coverage,
        "block_confidence": block_confidence,
        "block_raw": block_raw,
        "data_available": available > 0,
        "opponents": opponent_details,
        "reason": block.reason,
        "support_mode": block.support_mode,
    }


def compute_structural_coherence_v2(
    market_key: str,
    *,
    probs_by_market: dict[str, dict[str, float | None]],
) -> dict[str, Any]:
    """Multi-block S_FINAL with configured-strength denominator."""
    configured_blocks = blocks_for_market(market_key)
    block_results = [
        _evaluate_block(b, probs_by_market=probs_by_market) for b in configured_blocks
    ]

    if not configured_blocks:
        return {
            "component": "structural_coherence",
            "score": None,
            "S": None,
            "S_raw": None,
            "structural_confidence": None,
            "structural_status": "unavailable",
            "status": "unavailable",
            "structural_missing_penalty_applied": True,
            "structural_factor": STRUCTURAL_FACTOR_MISSING,
            "blocks": [],
            "formula": (
                "S_FINAL = 50 + SUM(block_confidence*(block_raw-50)) "
                "/ SUM(configured_strength)"
            ),
        }

    denom = sum(b.configured_strength for b in configured_blocks)
    available_blocks = [br for br in block_results if br["data_available"]]
    if not available_blocks or denom <= 0:
        return {
            "component": "structural_coherence",
            "score": None,
            "S": None,
            "S_raw": None,
            "structural_confidence": None,
            "structural_status": "unavailable",
            "status": "unavailable",
            "structural_missing_penalty_applied": True,
            "structural_factor": STRUCTURAL_FACTOR_MISSING,
            "blocks": block_results,
            "configured_block_count": len(configured_blocks),
            "available_block_count": 0,
            "formula": (
                "S_FINAL = 50 + SUM(block_confidence*(block_raw-50)) "
                "/ SUM(configured_strength)"
            ),
        }

    numerator = 0.0
    conf_sum = 0.0
    raw_weighted = 0.0
    for br in available_blocks:
        br_raw = float(br["block_raw"])
        br_conf = float(br["block_confidence"])
        numerator += br_conf * (br_raw - 50.0)
        conf_sum += br_conf
        raw_weighted += br_conf * br_raw

    s_final = clamp_v2(50.0 + numerator / denom, 0.0, 100.0)
    s_raw = clamp_v2(raw_weighted / conf_sum, 0.0, 100.0) if conf_sum > 0 else None
    structural_confidence = clamp_v2(conf_sum / denom, 0.0, 1.0)
    structural_factor = STRUCTURAL_FACTOR_BASE + STRUCTURAL_FACTOR_BASE * (
        s_final / 100.0
    )

    return {
        "component": "structural_coherence",
        "score": s_final,
        "S": s_final,
        "S_raw": s_raw,
        "structural_confidence": structural_confidence,
        "structural_status": "available",
        "status": "available",
        "structural_missing_penalty_applied": False,
        "structural_factor": structural_factor,
        "blocks": block_results,
        "configured_block_count": len(configured_blocks),
        "available_block_count": len(available_blocks),
        "configured_strength_sum": denom,
        "formula": (
            "S_FINAL = 50 + SUM(block_confidence*(block_raw-50)) "
            "/ SUM(configured_strength)"
        ),
    }


def structural_factor_from_s(s_block: dict[str, Any]) -> float:
    if s_block.get("status") != "available" or s_block.get("score") is None:
        return STRUCTURAL_FACTOR_MISSING
    return float(s_block["structural_factor"])


def _overround_penalty(overround: float | None) -> float:
    if overround is None:
        return 0.0
    ratio = (overround - Q_OVERROUND_BASE) / Q_OVERROUND_RANGE
    return Q_OVERROUND_MAX_PENALTY * clamp_v2(ratio, 0.0, 1.0)


def _extreme_divergence_penalty(abs_delta_logit: float) -> float:
    ratio = (
        abs_delta_logit - Q_EXTREME_DIVERGENCE_START
    ) / Q_EXTREME_DIVERGENCE_RANGE
    return Q_EXTREME_DIVERGENCE_MAX_PENALTY * clamp_v2(ratio, 0.0, 1.0)


def compute_information_quality_v2(
    *,
    overround: float | None,
    book_fallback_used: bool,
    fair_probability_may_be_derived: bool,
    delta_logit_value: float,
) -> dict[str, Any]:
    ov_pen = _overround_penalty(overround)
    fb_pen = Q_BOOK_FALLBACK_PENALTY if book_fallback_used else 0.0
    df_pen = Q_DERIVED_FAIR_PENALTY if fair_probability_may_be_derived else 0.0
    ex_pen = _extreme_divergence_penalty(abs(delta_logit_value))
    q_score = clamp_v2(100.0 - ov_pen - fb_pen - df_pen - ex_pen, 0.0, 100.0)
    quality_factor = QUALITY_FACTOR_BASE + QUALITY_FACTOR_BASE * (q_score / 100.0)
    return {
        "component": "information_quality",
        "score": q_score,
        "Q": q_score,
        "status": "available",
        "quality_factor": quality_factor,
        "penalties": {
            "overround_penalty": ov_pen,
            "fallback_penalty": fb_pen,
            "derived_fair_penalty": df_pen,
            "extreme_divergence_penalty": ex_pen,
        },
        "overround_penalty": ov_pen,
        "fallback_penalty": fb_pen,
        "derived_fair_penalty": df_pen,
        "extreme_divergence_penalty": ex_pen,
        "overround": overround,
        "book_fallback_used": book_fallback_used,
        "fair_probability_may_be_derived": fair_probability_may_be_derived,
        "formula": "clamp(100 - penalties, 0, 100)",
    }


def compute_adjusted_and_final(
    *,
    acquisition_core: float,
    structural_factor: float,
    quality_factor: float,
) -> dict[str, Any]:
    adjusted = acquisition_core * structural_factor * quality_factor
    final_raw = clamp_v2(adjusted, 0.0, 100.0)
    return {
        "adjusted_confidence": adjusted,
        "final_score_raw": final_raw,
        "display_transform": None,
        "formula": "final_score_raw = clamp(adjusted_confidence, 0, 100)",
    }
