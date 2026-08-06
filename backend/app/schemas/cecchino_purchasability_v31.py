"""Contratto Acquistabilità v3.1 — shadow candidate empirica.

Parallela a fixed_discount_v3. Non operativa. Non promuove V3.1.

Versioning:
  - empirical_v1 / candidate_1: formula storica bloccante (HR/100), preservata
  - empirical_v2 / candidate_2: storico non bloccante + multiplier neutrale (corrente)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- Frozen empirical v1 (riproducibile, non mutare matematica) ---
PURCHASABILITY_V31_CANDIDATE_VERSION_V1 = "cecchino_purchasability_v31_candidate_1"
PURCHASABILITY_V31_FORMULA_VERSION_V1 = (
    "cecchino_purchasability_v31_fixed_discount_empirical_v1"
)
PURCHASABILITY_V31_FORMULA_CONFIG_VERSION_V1 = "fixed_discount_v31_empirical_v1"
PURCHASABILITY_V31_AUDIT_VERSION_V1 = "cecchino_purchasability_v31_audit_v1"
PURCHASABILITY_V31_FEATURE_VERSION_V1 = "cecchino_purchasability_v31_features_v1"
PURCHASABILITY_V31_CONTRACT_VERSION_V1 = "cecchino_purchasability_v31_contract"
PURCHASABILITY_V31_SNAPSHOT_VERSION_V1 = "cecchino_purchasability_snapshot_v31"

# --- Current shadow empirical v2 ---
PURCHASABILITY_V31_CONTRACT_VERSION = "cecchino_purchasability_v31_contract_v2"
PURCHASABILITY_V31_FEATURE_VERSION = "cecchino_purchasability_v31_features_v2"
PURCHASABILITY_V31_CANDIDATE_VERSION = "cecchino_purchasability_v31_candidate_2"
PURCHASABILITY_V31_CANDIDATE_NAME = "purchasability_v31_shadow"
PURCHASABILITY_V31_FORMULA_VERSION = (
    "cecchino_purchasability_v31_fixed_discount_empirical_v2"
)
PURCHASABILITY_V31_FORMULA_CONFIG_VERSION = "fixed_discount_v31_empirical_v2"
PURCHASABILITY_V31_AUDIT_VERSION = "cecchino_purchasability_v31_audit_v2"
PURCHASABILITY_V31_SNAPSHOT_VERSION = "cecchino_purchasability_snapshot_v31_v2"
PURCHASABILITY_V31_REGISTRY_STATUS = "shadow_candidate"

PurchasabilityV31Status = Literal[
    "score",
    "score_provisional",
    "gate_failed",
    "non_calculable",
]

CalculationQuality = Literal["full", "partial", "provisional", "not_applicable"]

HistoricalEvidenceQuality = Literal[
    "definitive",
    "provisional",
    "neutral_fallback",
]

PurchasabilityClass = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
]

GateStatusV31 = Literal[
    "passed",
    "gate_failed",
    "unavailable_inputs",
]

QuotePerformanceType = Literal["real", "derived", "unavailable"]


class PurchasabilityV31DependencyMeta(BaseModel):
    rating_used_in_score: bool = False
    rating_used_as_gate: bool = True
    historical_reliability_used_as_factor: bool = True
    probability_advantage_used_as_weight: bool = False
    score_acquisto_used: bool = False
    linked_markets_used_in_score: bool = False
    fixed_scales_used: bool = True
    edge_used_in_value_score: bool = True
    mathematical_complement_used: bool = True
    derived_quote_blocks_score: bool = True


class PurchasabilityV31Item(BaseModel):
    formula_version: str = PURCHASABILITY_V31_FORMULA_VERSION
    formula_config_version: str = PURCHASABILITY_V31_FORMULA_CONFIG_VERSION
    candidate_name: str = PURCHASABILITY_V31_CANDIDATE_NAME
    candidate_version: str = PURCHASABILITY_V31_CANDIDATE_VERSION
    registry_status: str = PURCHASABILITY_V31_REGISTRY_STATUS
    audit_version: str = PURCHASABILITY_V31_AUDIT_VERSION
    market_key: str
    label: str | None = None
    market_family: str | None = None
    period: str | None = None
    line: float | None = None
    status: PurchasabilityV31Status | str = "non_calculable"
    calculation_quality: CalculationQuality | str | None = None
    gate_status: GateStatusV31 | str | None = None
    score: int | None = None
    raw_score: float | None = None
    class_: PurchasabilityClass | str | None = Field(default=None, alias="class")
    reading_short: str | None = None
    reading_detailed: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    historical_reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pre_match_only: bool = True
    current_operational_version: bool = False
    shadow_candidate: bool = True
    dependency_meta: PurchasabilityV31DependencyMeta = Field(
        default_factory=PurchasabilityV31DependencyMeta
    )

    model_config = {"populate_by_name": True}


class PurchasabilityV31Snapshot(BaseModel):
    snapshot_version: str = PURCHASABILITY_V31_SNAPSHOT_VERSION
    contract_version: str = PURCHASABILITY_V31_CONTRACT_VERSION
    feature_version: str = PURCHASABILITY_V31_FEATURE_VERSION
    candidate_version: str = PURCHASABILITY_V31_CANDIDATE_VERSION
    candidate_name: str = PURCHASABILITY_V31_CANDIDATE_NAME
    formula_version: str = PURCHASABILITY_V31_FORMULA_VERSION
    formula_config_version: str = PURCHASABILITY_V31_FORMULA_CONFIG_VERSION
    audit_version: str = PURCHASABILITY_V31_AUDIT_VERSION
    registry_status: str = PURCHASABILITY_V31_REGISTRY_STATUS
    status: Literal["ok", "partial", "unavailable"] | str = "unavailable"
    items: list[dict[str, object]] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    shadow_summary: dict[str, object] = Field(default_factory=dict)
    full_candidate_payload_sha256: str | None = None
    input_fingerprint: str | None = None
    generated_at: str | None = None
    source_snapshot_at: str | None = None
    source_snapshot_verified: bool | None = None
    source_snapshot_before_kickoff: bool | None = None
    source_mode: str | None = None
    pre_match_only: bool = True
    historical_reliability_integrated: bool = True
    fixed_scales_used: bool = True
    current_operational_version: bool = False
    shadow_candidate: bool = True
    contains_post_match_fields: bool = False
    signals_integration: bool = False
    warnings: list[str] = Field(default_factory=list)
