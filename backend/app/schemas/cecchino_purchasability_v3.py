"""Contratto Acquistabilità v3 — fixed-discount parallela a v1.1 e v2.

Non sostituisce v1.1 né v2. Nessun profilo storico. Scale fisse.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PURCHASABILITY_V3_CONTRACT_VERSION = "cecchino_purchasability_v3_contract"
PURCHASABILITY_V3_FEATURE_VERSION = "cecchino_purchasability_v3_features_v1"
PURCHASABILITY_V3_CANDIDATE_VERSION = "cecchino_purchasability_v3_candidate_1"
PURCHASABILITY_V3_CANDIDATE_NAME = "fixed_discount_v3"
PURCHASABILITY_V3_FORMULA_VERSION = "cecchino_purchasability_v3_fixed_discount_v1"
PURCHASABILITY_V3_AUDIT_VERSION = "cecchino_purchasability_v3_audit_v1"
PURCHASABILITY_V3_SNAPSHOT_VERSION = "cecchino_purchasability_snapshot_v3"
PURCHASABILITY_V3_REGISTRY_STATUS = "active_parallel_preview"

PurchasabilityV3Status = Literal[
    "available",
    "partial",
    "unavailable",
    "not_applicable",
]

CalculationQuality = Literal["full", "partial", "not_applicable"]

PurchasabilityClass = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
]

GateStatus = Literal[
    "passed",
    "failed_non_positive_edge",
    "failed_non_positive_probability_advantage",
    "failed_multiple_non_positive_components",
    "unavailable_inputs",
    "unsupported_market",
]

QuotePerformanceType = Literal["real", "derived", "unavailable"]

AmbiguityStatus = Literal[
    "leader_clear",
    "leader_close",
    "not_leader",
    "insufficient_family_comparison",
    "not_applicable",
]


class PurchasabilityV3Penalty(BaseModel):
    key: str
    label: str
    raw_inputs: dict[str, float | str | bool | None] = Field(default_factory=dict)
    threshold_start: float | None = None
    threshold_full: float | None = None
    severity: float | None = None
    max_points: float | None = None
    penalty_points: float | None = None
    applied: bool = False
    explanation: str | None = None


class PurchasabilityV3Gate(BaseModel):
    gate_status: GateStatus | str = "unavailable_inputs"
    gate_reason_codes: list[str] = Field(default_factory=list)
    edge_available: bool | None = None
    edge_positive: bool | None = None
    probability_advantage_available: bool | None = None
    probability_advantage_positive: bool | None = None
    gate_reading: str | None = None


class PurchasabilityV3LinkedMarketContext(BaseModel):
    linked_market_key: str | None = None
    relationship: str | None = None
    edge_pct: float | None = None
    vantaggio_prob: float | None = None
    rating: float | None = None
    gate_status: str | None = None
    used_in_score: bool = False
    diagnostic_only: bool = True


class PurchasabilityV3DependencyMeta(BaseModel):
    rating_used_in_score: bool = False
    probability_advantage_used_as_weight: bool = False
    score_acquisto_used: bool = False
    historical_profile_used: bool = False
    linked_markets_used_in_score: bool = False
    fixed_scales_used: bool = True
    edge_used_in_value_score: bool = True
    edge_used_in_family_ambiguity_only_as_comparison: bool = True
    book_opposite_used_only_in_opposite_penalty: bool = True
    probability_cecchino_used_in_risk_and_divergence_only: bool = True


class PurchasabilityV3Item(BaseModel):
    candidate_version: str = PURCHASABILITY_V3_CANDIDATE_VERSION
    formula_version: str = PURCHASABILITY_V3_FORMULA_VERSION
    audit_version: str = PURCHASABILITY_V3_AUDIT_VERSION
    market_key: str
    market_label: str | None = None
    market_family: str | None = None
    period: str | None = None
    line: float | None = None
    status: PurchasabilityV3Status | str = "unavailable"
    class_: PurchasabilityClass | str | None = Field(default=None, alias="class")
    calculation_quality: CalculationQuality | str | None = None
    gate_status: GateStatus | str | None = None
    score: int | None = None
    raw_score: float | None = None
    value_score: float | None = None
    quality_score: float | None = None
    reading_short: str | None = None
    reading_detailed: str | None = None
    historical_profile_used: bool = False
    fixed_scales_used: bool = True
    pre_match_only: bool = True
    parallel_candidate: bool = True
    current_operational_version: bool = False
    dependency_meta: PurchasabilityV3DependencyMeta = Field(
        default_factory=PurchasabilityV3DependencyMeta
    )
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PurchasabilityV3CompactItem(BaseModel):
    market_key: str
    market_label: str | None = None
    market_family: str | None = None
    status: PurchasabilityV3Status | str = "unavailable"
    calculation_quality: CalculationQuality | str | None = None
    score: int | None = None
    raw_score: float | None = None
    class_: PurchasabilityClass | str | None = Field(default=None, alias="class")
    gate_status: GateStatus | str | None = None
    value_score: float | None = None
    quality_score: float | None = None
    total_penalty: float | None = None
    reading_short: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    historical_profile_used: bool = False
    fixed_scales_used: bool = True

    model_config = {"populate_by_name": True}


class PurchasabilityV3Snapshot(BaseModel):
    snapshot_version: str = PURCHASABILITY_V3_SNAPSHOT_VERSION
    contract_version: str = PURCHASABILITY_V3_CONTRACT_VERSION
    feature_version: str = PURCHASABILITY_V3_FEATURE_VERSION
    candidate_version: str = PURCHASABILITY_V3_CANDIDATE_VERSION
    candidate_name: str = PURCHASABILITY_V3_CANDIDATE_NAME
    formula_version: str = PURCHASABILITY_V3_FORMULA_VERSION
    audit_version: str = PURCHASABILITY_V3_AUDIT_VERSION
    registry_status: str = PURCHASABILITY_V3_REGISTRY_STATUS
    status: Literal["ok", "partial", "unavailable"] | str = "unavailable"
    items: list[dict[str, object]] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    full_candidate_payload_sha256: str | None = None
    generated_at: str | None = None
    source_snapshot_at: str | None = None
    source_snapshot_verified: bool | None = None
    source_snapshot_before_kickoff: bool | None = None
    source_mode: str | None = None
    pre_match_only: bool = True
    historical_profile_used: bool = False
    fixed_scales_used: bool = True
    current_operational_version: bool = False
    parallel_candidate: bool = True
    contains_post_match_fields: bool = False
    signals_integration: bool = False
    warnings: list[str] = Field(default_factory=list)
