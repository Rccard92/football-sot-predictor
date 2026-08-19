"""Configurazione Cecchino Purchasability V3.5 — scale, pesi, gate, versioning."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION,
    PURCHASABILITY_V35_CONTRACT_VERSION,
    PURCHASABILITY_V35_FEATURE_VERSION,
    PURCHASABILITY_V35_FORMULA_VERSION,
    PURCHASABILITY_V35_RELATION_REGISTRY_VERSION,
)

# --- Version strings (re-export for convenience) ---
CONTRACT_VERSION = PURCHASABILITY_V35_CONTRACT_VERSION
FEATURE_VERSION = PURCHASABILITY_V35_FEATURE_VERSION
FORMULA_VERSION = PURCHASABILITY_V35_FORMULA_VERSION
RELATION_REGISTRY_VERSION = PURCHASABILITY_V35_RELATION_REGISTRY_VERSION
CANDIDATE_REGISTRY_VERSION = PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION

# --- Component scales ---
V_EXECUTABLE_VALUE_SCALE = 0.30
D_MARKET_DISAGREEMENT_SCALE = 0.55
S_STRUCTURAL_SUPPORT_SCALE = 0.45
PROB_EPSILON = 1e-6

# --- Gate ---
RATING_MIN_GATE = 50.0

# --- Q penalties ---
Q_OVERROUND_BASE = 0.04
Q_OVERROUND_RANGE = 0.12
Q_OVERROUND_MAX_PENALTY = 25.0
Q_BOOK_FALLBACK_PENALTY = 10.0
Q_DERIVED_FAIR_PENALTY = 10.0
Q_EXTREME_DIVERGENCE_START = 1.25
Q_EXTREME_DIVERGENCE_RANGE = 1.25
Q_EXTREME_DIVERGENCE_MAX_PENALTY = 20.0

# --- Display classes (descriptive only, not gates) ---
CLASS_THRESHOLDS = (20, 40, 60, 80)

# --- Candidate registry ---
CANDIDATE_IDS: dict[str, str] = {
    "A": "v35_a_balanced_structural_v1",
    "B": "v35_b_value_heavy_v1",
    "C": "v35_c_structure_heavy_v1",
    "D": "v35_d_quality_conservative_v1",
}

CANDIDATE_NAMES: dict[str, str] = {
    "A": "V3.5-A Balanced Structural",
    "B": "V3.5-B Value Heavy",
    "C": "V3.5-C Structure Heavy",
    "D": "V3.5-D Quality Conservative",
}

_COMPONENT_KEYS = ("V", "D", "S", "Q")

_CANDIDATE_WEIGHTS_RAW: dict[str, dict[str, float]] = {
    "A": {"V": 0.40, "D": 0.25, "S": 0.20, "Q": 0.15},
    "B": {"V": 0.55, "D": 0.20, "S": 0.15, "Q": 0.10},
    "C": {"V": 0.35, "D": 0.20, "S": 0.30, "Q": 0.15},
    "D": {"V": 0.35, "D": 0.20, "S": 0.15, "Q": 0.30},
}

CANDIDATE_WEIGHTS = MappingProxyType(
    {k: MappingProxyType(dict(v)) for k, v in _CANDIDATE_WEIGHTS_RAW.items()}
)

# --- Anti-leakage ---
V35_FORBIDDEN_INPUT_KEYS = frozenset(
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
        "historical_reliability",
        "historical_reliability_score",
        "result_json",
        "profit_1u_real",
        "profit_1u_synthetic",
        "settlement_status",
        "ft_result",
        "ht_result",
        "home_score_ft",
        "away_score_ft",
    }
)

V35_ALLOWED_ROW_KEYS = frozenset(
    {
        "market_key",
        "segno",
        "label",
        "quota_book",
        "quota_cecchino",
        "prob_cecchino",
        "prob_book",
        "vantaggio_prob",
        "edge_pct",
        "rating",
        "rating_label",
        "status",
        "book_source",
        "odds_source",
        "quote_source",
        "cecchino_source",
        "bookmaker_name",
        "provider_bookmaker_id",
        "book_fallback_used",
        "derived_quote",
        "not_real_book_quote",
        "force_derived_quote",
    }
)

# --- Gate reason codes ---
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

# --- Execution quote derived markers (local copy, no V3.1 import) ---
_DERIVED_BOOK_SOURCE_MARKERS = (
    "derived",
    "synthetic",
    "reconstructed",
    "model",
    "from_1x2",
    "from_betfair_1x2",
)

SOURCE_DC_DERIVED = "derived_double_chance_from_normalized_1x2"

# --- Market labels (display) ---
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


def market_label_for(market_key: str) -> str:
    return MARKET_LABELS.get(market_key, market_key)


def version_meta() -> dict[str, str]:
    return {
        "contract_version": CONTRACT_VERSION,
        "feature_version": FEATURE_VERSION,
        "formula_version": FORMULA_VERSION,
        "relation_registry_version": RELATION_REGISTRY_VERSION,
        "candidate_registry_version": CANDIDATE_REGISTRY_VERSION,
    }


def dependency_meta() -> dict[str, Any]:
    return {
        "rating_used_in_score": False,
        "rating_used_as_gate": True,
        "historical_reliability_used": False,
        "score_acquisto_used": False,
        "v3_score_used": False,
        "v31_score_used": False,
        "edge_used_in_gate": False,
        "vantaggio_prob_used_in_gate": False,
        "structural_relations_used_in_score": True,
        "deterministic_complements_excluded": True,
        "pre_match_only": True,
    }
