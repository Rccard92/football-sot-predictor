"""Versioni canoniche Bet Builder — orchestrazione read-only, non un nuovo modello."""

from __future__ import annotations

BET_BUILDER_CONTRACT_VERSION = "cecchino_bet_builder_contract_v1"
# v2 = price gate aligned to V3.1 theoretical gate
BET_BUILDER_AGGREGATOR_VERSION = "cecchino_bet_builder_opportunity_aggregator_v2"
BET_BUILDER_SIGNAL_EVIDENCE_VERSION = "cecchino_bet_builder_signal_evidence_v1"
BET_BUILDER_PURCHASABILITY_POLICY_VERSION = (
    "cecchino_bet_builder_purchasability_v31_only_v1"
)

PURCHASABILITY_POLICY = "v31_only"

PRICE_VALUE_METHOD = "v31_theoretical_gate_v1"

ORIGIN_PRICE = "price"
ORIGIN_SIGNALS = "signals"
ORIGIN_PRICE_AND_SIGNALS = "price_and_signals"

FRESHNESS_WARNING_SCAN_IN_PROGRESS = "cecchino_today_scan_in_progress"

REASON_PURCHASABILITY_V31_UNAVAILABLE = "purchasability_v31_unavailable"
REASON_NO_VALIDATED_CONTEXT_MODULE = "no_validated_context_module"
REASON_NO_CANONICAL_RAW_SIGNAL_MAPPING = "no_canonical_raw_signal_mapping"
REASON_SIGNALS_MATRIX_UNAVAILABLE = "signals_matrix_unavailable"
REASON_SIGNALS_FORMULA_NOT_CURRENT = "signals_formula_not_current"
