"""Contratto Acquistabilità V3.5 — motore strutturale shadow (V/D/S/Q + A/B/C/D).

Isolato da V3.1. Snapshot live experiment via purchasability_preview_v35.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PURCHASABILITY_V35_CONTRACT_VERSION = "cecchino_purchasability_v35_contract_v1"
PURCHASABILITY_V35_FEATURE_VERSION = "cecchino_purchasability_v35_features_v1"
PURCHASABILITY_V35_FORMULA_VERSION = "cecchino_purchasability_v35_structural_v1"
PURCHASABILITY_V35_RELATION_REGISTRY_VERSION = (
    "cecchino_purchasability_v35_relations_v1"
)
PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION = (
    "cecchino_purchasability_v35_candidates_v1"
)
PURCHASABILITY_V35_REGISTRY_STATUS = "shadow_engine"
PURCHASABILITY_V35_SNAPSHOT_VERSION = "cecchino_purchasability_v35_snapshot_v1"
PURCHASABILITY_V35_EXPERIMENT_VERSION = (
    "cecchino_purchasability_v35_live_experiment_v1"
)
PURCHASABILITY_V35_SNAPSHOT_REGISTRY_STATUS = "shadow_live_experiment"
PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION = (
    "cecchino_purchasability_v35_audit_export_v1"
)
PURCHASABILITY_V35_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION = (
    "cecchino_purchasability_v35_daily_audit_manifest_v1"
)

PurchasabilityV35Status = Literal[
    "score",
    "gate_failed",
    "not_calculable",
]

GateStatusV35 = Literal[
    "passed",
    "gate_failed",
    "unavailable_inputs",
]

StructuralStatusV35 = Literal[
    "available",
    "unavailable",
]

PurchasabilityClassV35 = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
]


class PurchasabilityV35DependencyMeta(BaseModel):
    rating_used_in_score: bool = False
    rating_used_as_gate: bool = True
    historical_reliability_used: bool = False
    score_acquisto_used: bool = False
    v3_score_used: bool = False
    v31_score_used: bool = False
    edge_used_in_gate: bool = False
    vantaggio_prob_used_in_gate: bool = False
    structural_relations_used_in_score: bool = True
    deterministic_complements_excluded: bool = True
    pre_match_only: bool = True


class PurchasabilityV35Item(BaseModel):
    contract_version: str = PURCHASABILITY_V35_CONTRACT_VERSION
    feature_version: str = PURCHASABILITY_V35_FEATURE_VERSION
    formula_version: str = PURCHASABILITY_V35_FORMULA_VERSION
    relation_registry_version: str = PURCHASABILITY_V35_RELATION_REGISTRY_VERSION
    candidate_registry_version: str = PURCHASABILITY_V35_CANDIDATE_REGISTRY_VERSION
    registry_status: str = PURCHASABILITY_V35_REGISTRY_STATUS
    market_key: str
    label: str | None = None
    status: PurchasabilityV35Status | str = "not_calculable"
    gate_status: GateStatusV35 | str | None = None
    pre_match_only: bool = True
    contains_post_match_fields: bool = False
