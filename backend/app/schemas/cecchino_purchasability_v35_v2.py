"""Contratto Acquistabilità V3.5 Structural V2 — Value × Base-rate Reliability × S × Q.

Isolato da structural_v1. Nessun candidate A/B/C/D.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

PURCHASABILITY_V35_V2_CONTRACT_VERSION = "cecchino_purchasability_v35_v2_contract_v1"
PURCHASABILITY_V35_V2_FEATURE_VERSION = "cecchino_purchasability_v35_v2_features_v1"
PURCHASABILITY_V35_V2_FORMULA_VERSION = "cecchino_purchasability_v35_structural_v2"
PURCHASABILITY_V35_V2_RELATION_REGISTRY_VERSION = (
    "cecchino_purchasability_v35_relations_v2"
)
PURCHASABILITY_V35_V2_SNAPSHOT_VERSION = "cecchino_purchasability_v35_v2_snapshot_v1"
PURCHASABILITY_V35_V2_EXPERIMENT_VERSION = (
    "cecchino_purchasability_v35_live_experiment_v2"
)
PURCHASABILITY_V35_V2_REGISTRY_STATUS = "shadow_engine"
PURCHASABILITY_V35_V2_SNAPSHOT_REGISTRY_STATUS = "shadow_live_experiment"
PURCHASABILITY_V35_V2_REFERENCE_ID = "v35_structural_v2_reference"
PURCHASABILITY_V35_V2_REFERENCE_LABEL = "V3.5 Structural V2"
PURCHASABILITY_V35_V2_AUDIT_EXPORT_CONTRACT_VERSION = (
    "cecchino_purchasability_v35_v2_audit_export_v1"
)
PURCHASABILITY_V35_V2_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION = (
    "cecchino_purchasability_v35_v2_daily_audit_manifest_v1"
)
PURCHASABILITY_V35_V2_ANALYSIS_EXPORT_CONTRACT_VERSION = (
    "cecchino_purchasability_v35_v2_analysis_export_v1"
)
PURCHASABILITY_V35_V2_ANALYSIS_MANIFEST_CONTRACT_VERSION = (
    "cecchino_purchasability_v35_v2_analysis_manifest_v2"
)

PurchasabilityV35V2Status = Literal[
    "score",
    "gate_failed",
    "not_calculable",
]

GateStatusV35V2 = Literal[
    "passed",
    "gate_failed",
    "unavailable_inputs",
]

StructuralStatusV35V2 = Literal[
    "available",
    "unavailable",
]

PurchasabilityClassV35V2 = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
    "Eccezionale",
]


class PurchasabilityV35V2DependencyMeta(BaseModel):
    rating_used_in_score: bool = False
    rating_used_as_gate: bool = True
    historical_reliability_used: bool = False
    score_acquisto_used: bool = False
    v3_score_used: bool = False
    v31_score_used: bool = False
    v35_v1_score_used: bool = False
    edge_used_in_gate: bool = False
    vantaggio_prob_used_in_gate: bool = False
    structural_relations_used_in_score: bool = True
    deterministic_complements_excluded: bool = True
    pre_match_only: bool = True
    base_rate_reliability_is_calibrated_probability: bool = False
    candidates_abcd_used: bool = False
