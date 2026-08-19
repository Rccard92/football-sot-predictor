"""Componenti V/D/S/Q — Cecchino Purchasability V3.5."""

from __future__ import annotations

import math
from typing import Any

from app.services.cecchino.cecchino_purchasability_statistical_helpers import (
    clip_prob,
)
from app.services.cecchino.cecchino_purchasability_v35_config import (
    D_MARKET_DISAGREEMENT_SCALE,
    PROB_EPSILON,
    Q_BOOK_FALLBACK_PENALTY,
    Q_DERIVED_FAIR_PENALTY,
    Q_EXTREME_DIVERGENCE_MAX_PENALTY,
    Q_EXTREME_DIVERGENCE_RANGE,
    Q_EXTREME_DIVERGENCE_START,
    Q_OVERROUND_BASE,
    Q_OVERROUND_MAX_PENALTY,
    Q_OVERROUND_RANGE,
    S_STRUCTURAL_SUPPORT_SCALE,
    V_EXECUTABLE_VALUE_SCALE,
)
from app.services.cecchino.cecchino_purchasability_v35_features import (
    is_valid_open_probability,
    resolve_probability_cecchino,
)
from app.services.cecchino.cecchino_purchasability_v35_relations import (
    scoreable_relations_for_market,
)
from app.services.cecchino.cecchino_purchasability_v35_utils import clamp_v35


def logit(p: float, *, epsilon: float = PROB_EPSILON) -> float:
    clipped = clip_prob(p, eps=epsilon)
    return math.log(clipped / (1.0 - clipped))


def delta_logit(p_model: float, p_fair: float) -> float:
    return logit(p_model) - logit(p_fair)


def compute_executable_value(expected_value: float) -> dict[str, Any]:
    """V = 100 × (1 - exp(-EV / 0.30)), clamp 0–100."""
    if expected_value <= 0:
        score = 0.0
    else:
        score = 100.0 * (1.0 - math.exp(-expected_value / V_EXECUTABLE_VALUE_SCALE))
    score = clamp_v35(score, 0.0, 100.0)
    return {
        "component": "executable_value",
        "expected_value": expected_value,
        "executable_value_score": score,
        "scale": V_EXECUTABLE_VALUE_SCALE,
        "formula": "100 * (1 - exp(-EV / scale))",
        "score": score,
        "status": "available",
    }


def compute_market_disagreement(
    probability_cecchino: float,
    fair_book_probability: float,
) -> dict[str, Any]:
    """D = 100 × (1 - exp(-delta_logit / 0.55)) for delta > 0."""
    dl = delta_logit(probability_cecchino, fair_book_probability)
    if dl <= 0:
        d_score = 0.0
    else:
        d_score = 100.0 * (1.0 - math.exp(-dl / D_MARKET_DISAGREEMENT_SCALE))
    d_score = clamp_v35(d_score, 0.0, 100.0)
    return {
        "component": "market_disagreement",
        "delta_logit": dl,
        "market_disagreement_score": d_score,
        "scale": D_MARKET_DISAGREEMENT_SCALE,
        "formula": "100 * (1 - exp(-delta_logit / scale))",
        "score": d_score,
        "status": "available",
    }


def _related_support_score(related_delta: float) -> float:
    return clamp_v35(
        50.0 + 50.0 * math.tanh(related_delta / S_STRUCTURAL_SUPPORT_SCALE),
        0.0,
        100.0,
    )


def compute_structural_coherence(
    market_key: str,
    *,
    by_mk: dict[str, dict[str, Any]],
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None] | None,
) -> dict[str, Any]:
    """S_raw weighted mean + structural_confidence attenuation → S_effective."""
    configured_relations = scoreable_relations_for_market(market_key)
    configured_relation_count = len(configured_relations)
    relation_details: list[dict[str, Any]] = []
    weighted_sum = 0.0
    weight_sum = 0.0
    available_weights: list[float] = []

    for rel in configured_relations:
        related_mk = rel.related_market
        related_row = by_mk.get(related_mk) or {}
        related_fair = fair_by.get(related_mk)
        p_related = resolve_probability_cecchino(related_row, model_probs, related_mk)
        p_fair_related = None
        if isinstance(related_fair, dict) and related_fair.get(
            "fair_book_probability_verified"
        ):
            try:
                p_fair_related = float(related_fair["fair_book_probability"])
            except (TypeError, ValueError):
                p_fair_related = None

        detail: dict[str, Any] = {
            "related_market": related_mk,
            "relation_type": rel.relation_type,
            "relation_weight": rel.relation_weight,
            "used_in_score": rel.used_in_score,
            "reason": rel.reason,
            "related_delta_logit": None,
            "support_score": None,
            "data_available": False,
        }

        if (
            p_related is not None
            and p_fair_related is not None
            and is_valid_open_probability(p_related)
            and is_valid_open_probability(p_fair_related)
        ):
            rd = delta_logit(p_related, p_fair_related)
            support = _related_support_score(rd)
            detail["related_delta_logit"] = rd
            detail["support_score"] = support
            detail["data_available"] = True
            weighted_sum += support * rel.relation_weight
            weight_sum += rel.relation_weight
            available_weights.append(rel.relation_weight)

        relation_details.append(detail)

    if configured_relation_count == 0 or weight_sum <= 0:
        return {
            "component": "structural_coherence",
            "score": None,
            "raw_score": None,
            "structural_confidence": None,
            "relation_strength": None,
            "coverage": None,
            "configured_relation_count": configured_relation_count,
            "available_relation_count": 0,
            "structural_status": "unavailable",
            "status": "unavailable",
            "scale": S_STRUCTURAL_SUPPORT_SCALE,
            "formula": "S_effective = 50 + (S_raw - 50) * structural_confidence",
            "relations": relation_details,
        }

    available_relation_count = len(available_weights)
    s_raw = clamp_v35(weighted_sum / weight_sum, 0.0, 100.0)
    relation_strength = clamp_v35(
        sum(available_weights) / available_relation_count,
        0.0,
        1.0,
    )
    coverage = available_relation_count / configured_relation_count
    structural_confidence = clamp_v35(relation_strength * coverage, 0.0, 1.0)
    s_effective = clamp_v35(
        50.0 + (s_raw - 50.0) * structural_confidence,
        0.0,
        100.0,
    )

    return {
        "component": "structural_coherence",
        "score": s_effective,
        "raw_score": s_raw,
        "structural_confidence": structural_confidence,
        "relation_strength": relation_strength,
        "coverage": coverage,
        "configured_relation_count": configured_relation_count,
        "available_relation_count": available_relation_count,
        "structural_status": "available",
        "status": "available",
        "scale": S_STRUCTURAL_SUPPORT_SCALE,
        "formula": "S_effective = 50 + (S_raw - 50) * structural_confidence",
        "relations": relation_details,
    }


def _overround_penalty(overround: float | None) -> float:
    if overround is None:
        return 0.0
    ratio = (overround - Q_OVERROUND_BASE) / Q_OVERROUND_RANGE
    return Q_OVERROUND_MAX_PENALTY * clamp_v35(ratio, 0.0, 1.0)


def _extreme_divergence_penalty(abs_delta_logit: float) -> float:
    ratio = (abs_delta_logit - Q_EXTREME_DIVERGENCE_START) / Q_EXTREME_DIVERGENCE_RANGE
    return Q_EXTREME_DIVERGENCE_MAX_PENALTY * clamp_v35(ratio, 0.0, 1.0)


def compute_information_quality(
    *,
    overround: float | None,
    book_fallback_used: bool,
    fair_probability_may_be_derived: bool,
    delta_logit_value: float,
    hours_to_kickoff: float | None,
) -> dict[str, Any]:
    """Q = 100 - penalties, clamp 0–100."""
    ov_pen = _overround_penalty(overround)
    fb_pen = Q_BOOK_FALLBACK_PENALTY if book_fallback_used else 0.0
    df_pen = Q_DERIVED_FAIR_PENALTY if fair_probability_may_be_derived else 0.0
    ex_pen = _extreme_divergence_penalty(abs(delta_logit_value))

    q_raw = 100.0 - ov_pen - fb_pen - df_pen - ex_pen
    q_score = clamp_v35(q_raw, 0.0, 100.0)

    return {
        "component": "information_quality",
        "score": q_score,
        "status": "available",
        "overround_penalty": ov_pen,
        "fallback_penalty": fb_pen,
        "derived_fair_penalty": df_pen,
        "extreme_divergence_penalty": ex_pen,
        "overround": overround,
        "book_fallback_used": book_fallback_used,
        "fair_probability_may_be_derived": fair_probability_may_be_derived,
        "hours_to_kickoff": hours_to_kickoff,
        "snapshot_age_used_in_score": False,
        "formula": "clamp(100 - penalties, 0, 100)",
    }
