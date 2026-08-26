"""Configurazione Cecchino Purchasability V3.5 Structural V2."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_CONTRACT_VERSION,
    PURCHASABILITY_V35_V2_EXPERIMENT_VERSION,
    PURCHASABILITY_V35_V2_FEATURE_VERSION,
    PURCHASABILITY_V35_V2_FORMULA_VERSION,
    PURCHASABILITY_V35_V2_REFERENCE_ID,
    PURCHASABILITY_V35_V2_REFERENCE_LABEL,
    PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION,
    PURCHASABILITY_V35_V2_SNAPSHOT_VERSION,
)

# Declared for Phase B wiring only — Phase A must NOT activate scan attach.
ACTIVE_V35_STRUCTURAL_VERSION = "v2"

CONTRACT_VERSION = PURCHASABILITY_V35_V2_CONTRACT_VERSION
FEATURE_VERSION = PURCHASABILITY_V35_V2_FEATURE_VERSION
FORMULA_VERSION = PURCHASABILITY_V35_V2_FORMULA_VERSION
RELATION_REGISTRY_VERSION = PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION
SNAPSHOT_VERSION = PURCHASABILITY_V35_V2_SNAPSHOT_VERSION
EXPERIMENT_VERSION = PURCHASABILITY_V35_V2_EXPERIMENT_VERSION
REFERENCE_ID = PURCHASABILITY_V35_V2_REFERENCE_ID
REFERENCE_LABEL = PURCHASABILITY_V35_V2_REFERENCE_LABEL

# --- Component scales ---
V_SCALE_V2 = 0.60
D_SCALE_V2 = 0.85
S_SUPPORT_SCALE_V2 = 0.45
PROB_EPSILON = 1e-6

VALUE_CORE_V_WEIGHT = 0.55
VALUE_CORE_D_WEIGHT = 0.45

STRUCTURAL_FACTOR_MISSING = 0.55
STRUCTURAL_FACTOR_BASE = 0.50
QUALITY_FACTOR_BASE = 0.50

# Evidence block strengths (configured)
STRENGTH_SAME_FAMILY_OPPOSITION = 0.75
STRENGTH_SIDE_COVER = 0.60
STRENGTH_GOAL_LADDER = 1.00

# --- Gate (unchanged vs V1) ---
RATING_MIN_GATE = 50.0

# --- Q2 penalties ---
Q_OVERROUND_BASE = 0.03
Q_OVERROUND_RANGE = 0.12
Q_OVERROUND_MAX_PENALTY = 35.0
Q_BOOK_FALLBACK_PENALTY = 20.0
Q_DERIVED_FAIR_PENALTY = 15.0
Q_EXTREME_DIVERGENCE_START = 0.90
Q_EXTREME_DIVERGENCE_RANGE = 1.10
Q_EXTREME_DIVERGENCE_MAX_PENALTY = 30.0

# Class thresholds: <40, <50, <60, <70, <80, else Eccezionale
CLASS_THRESHOLDS = (40, 50, 60, 70, 80)

MARKET_LABELS: dict[str, str] = {
    "HOME": "1",
    "DRAW": "X",
    "AWAY": "2",
    "HOME_PT": "1 PT",
    "DRAW_PT": "X PT",
    "AWAY_PT": "2 PT",
    "ONE_X": "1X",
    "X_TWO": "X2",
    "ONE_TWO": "12",
    "OVER_1_5": "Over 1.5",
    "UNDER_1_5": "Under 1.5",
    "OVER_2_5": "Over 2.5",
    "UNDER_2_5": "Under 2.5",
    "OVER_3_5": "Over 3.5",
    "UNDER_3_5": "Under 3.5",
    "OVER_PT_0_5": "Over 0.5 PT",
    "UNDER_PT_0_5": "Under 0.5 PT",
    "OVER_PT_1_5": "Over 1.5 PT",
    "UNDER_PT_1_5": "Under 1.5 PT",
}

V35_V2_FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "result",
        "outcome",
        "final_score",
        "goals_home",
        "goals_away",
        "settlement",
        "won",
        "lost",
        "selection_won",
        "selection_lost",
        "unit_stake_profit",
        "v3_score",
        "v31_score",
        "score_acquisto",
        "score_A",
        "score_B",
        "score_C",
        "score_D",
        "raw_A",
        "raw_B",
        "raw_C",
        "raw_D",
        "historical_reliability",
        "historical_reliability_score",
        "result_json",
        "profit_1u",
        "profit_1u_real",
        "profit_1u_synthetic",
        "settlement_status",
        "ft_result",
        "ht_result",
        "home_score_ft",
        "away_score_ft",
        "ht_home",
        "ht_away",
        "ft_home",
        "ft_away",
        "match_status",
        "evaluation_reason",
        "break_even_probability",
    }
)

GATE_REASON_MISSING_EXECUTION_QUOTE = "missing_execution_quote"
GATE_REASON_EXECUTION_QUOTE_NOT_REAL = "execution_quote_not_real"
GATE_REASON_INVALID_EXECUTION_QUOTE = "invalid_execution_quote"
GATE_REASON_MISSING_MODEL_PROBABILITY = "missing_model_probability"
GATE_REASON_MISSING_FAIR_BOOK_PROBABILITY = "missing_fair_book_probability"
GATE_REASON_INVALID_PROBABILITY = "invalid_probability"
GATE_REASON_INCOMPLETE_MARKET = "incomplete_market"
GATE_REASON_RATING_MISSING = "rating_missing"
GATE_REASON_RATING_BELOW_50 = "rating_below_50"
GATE_REASON_NON_POSITIVE_EV = "non_positive_expected_value"
GATE_REASON_MODEL_NOT_ABOVE_FAIR = "model_not_above_fair_book"
GATE_REASON_INVALID_PRE_MATCH_SNAPSHOT = "invalid_pre_match_snapshot"

SOURCE_DC_DERIVED = "derived_double_chance_from_normalized_1x2"


def market_label_for(market_key: str) -> str:
    return MARKET_LABELS.get(market_key, market_key)


def version_meta() -> dict[str, str]:
    return {
        "contract_version": CONTRACT_VERSION,
        "feature_version": FEATURE_VERSION,
        "formula_version": FORMULA_VERSION,
        "relation_registry_version": RELATION_REGISTRY_VERSION,
    }


def dependency_meta() -> dict[str, Any]:
    return {
        "rating_used_in_score": False,
        "rating_used_as_gate": True,
        "historical_reliability_used": False,
        "score_acquisto_used": False,
        "v3_score_used": False,
        "v31_score_used": False,
        "v35_v1_score_used": False,
        "edge_used_in_gate": False,
        "vantaggio_prob_used_in_gate": False,
        "structural_relations_used_in_score": True,
        "deterministic_complements_excluded": True,
        "pre_match_only": True,
        "base_rate_reliability_is_calibrated_probability": False,
        "candidates_abcd_used": False,
    }


def frozen_math_config_v35_v2() -> dict[str, Any]:
    """Config matematica congelabile — input del fingerprint freeze."""
    return {
        "formula_version": FORMULA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "feature_version": FEATURE_VERSION,
        "relation_registry_version": RELATION_REGISTRY_VERSION,
        "reference_id": REFERENCE_ID,
        "reference_label": REFERENCE_LABEL,
        "scales": {
            "V": V_SCALE_V2,
            "D": D_SCALE_V2,
            "S_support": S_SUPPORT_SCALE_V2,
        },
        "value_core_weights": {
            "V": VALUE_CORE_V_WEIGHT,
            "D": VALUE_CORE_D_WEIGHT,
        },
        "structural": {
            "factor_base": STRUCTURAL_FACTOR_BASE,
            "factor_missing": STRUCTURAL_FACTOR_MISSING,
            "strengths": {
                "same_family_opposition": STRENGTH_SAME_FAMILY_OPPOSITION,
                "side_cover": STRENGTH_SIDE_COVER,
                "goal_ladder": STRENGTH_GOAL_LADDER,
            },
            "s_final_formula": (
                "50 + SUM(block_confidence*(block_raw-50)) "
                "/ SUM(configured_strength)"
            ),
            "final_score_raw_formula": "clamp(adjusted_confidence, 0, 100)",
            "display_transform": None,
        },
        "quality": {
            "factor_base": QUALITY_FACTOR_BASE,
            "overround_base": Q_OVERROUND_BASE,
            "overround_range": Q_OVERROUND_RANGE,
            "overround_max_penalty": Q_OVERROUND_MAX_PENALTY,
            "book_fallback_penalty": Q_BOOK_FALLBACK_PENALTY,
            "derived_fair_penalty": Q_DERIVED_FAIR_PENALTY,
            "extreme_divergence_start": Q_EXTREME_DIVERGENCE_START,
            "extreme_divergence_range": Q_EXTREME_DIVERGENCE_RANGE,
            "extreme_divergence_max_penalty": Q_EXTREME_DIVERGENCE_MAX_PENALTY,
        },
        "gate": {
            "rating_min": RATING_MIN_GATE,
            "rating_used_in_score": False,
        },
        "class_thresholds": list(CLASS_THRESHOLDS),
        "active_v35_structural_version_declared": ACTIVE_V35_STRUCTURAL_VERSION,
        "active_v35_structural_version_wired": False,
    }


def compute_v2_formula_freeze_sha256(config: dict[str, Any] | None = None) -> str:
    payload = config if config is not None else frozen_math_config_v35_v2()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def frozen_config_v35_v2() -> dict[str, Any]:
    cfg = frozen_math_config_v35_v2()
    cfg["formula_freeze_sha256"] = compute_v2_formula_freeze_sha256(cfg)
    return cfg
