"""Contratto Acquistabilità v2 — decision_quality_v2 (parallela a v1.1).

Non sostituisce cecchino_purchasability_v1_preview_contract.
Validation baseline resta candidate_2 / balanced_geometric_v1_1.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PURCHASABILITY_V2_CONTRACT_VERSION = "cecchino_purchasability_v2_contract"
PURCHASABILITY_V2_FEATURE_VERSION = "cecchino_purchasability_v2_features_v1"
PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION = (
    "cecchino_purchasability_v2_candidate_1"
)
PURCHASABILITY_DECISION_V2_CANDIDATE_NAME = "decision_quality_v2"
PURCHASABILITY_V2_SNAPSHOT_VERSION = "cecchino_purchasability_snapshot_v2"
PURCHASABILITY_V2_NORM_PROFILE_VERSION = (
    "cecchino_purchasability_v2_norm_profile_2026_07_26_v1"
)
PURCHASABILITY_V2_NORM_PROFILE_CUTOFF = "2026-07-26"
PURCHASABILITY_V2_REGISTRY_STATUS = "active_parallel_preview"
PURCHASABILITY_V1_1_VALIDATION_BASELINE_STATUS = "active_validation_baseline"

PurchasabilityV2Status = Literal[
    "available",
    "partial",
    "unavailable",
]

CalculationQuality = Literal["full", "partial"]

PurchasabilityClass = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
]

GateStatus = Literal["passed", "failed", "unavailable"]

CapSource = Literal[
    "historical_scope",
    "historical_global_fallback",
    "provisional_versioned_fallback",
]


class PurchasabilityV2NormTrace(BaseModel):
    raw_value: float | None = None
    normalized_value: float | None = None
    positive_cap: float | None = None
    negative_cap: float | None = None
    profile_scope: str | None = None
    profile_version: str | None = None
    sample_total: int | None = None
    sample_positive: int | None = None
    sample_negative: int | None = None
    cap_source: CapSource | str | None = None
    clipping_applied: bool | None = None


class PurchasabilityV2Phase1Component(BaseModel):
    raw_value: float | None = None
    normalized_value: float | None = None
    configured_weight: float | None = None
    applied_weight: float | None = None
    contribution: float | None = None
    status: str | None = None
    normalization: PurchasabilityV2NormTrace | None = None


class PurchasabilityV2Phase1Value(BaseModel):
    score: float | None = None
    status: PurchasabilityV2Status | str = "unavailable"
    configured_weights: dict[str, float] = Field(default_factory=dict)
    applied_weights: dict[str, float] = Field(default_factory=dict)
    coverage_ratio: float | None = None
    available_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    minimum_coverage_met: bool | None = None
    components: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)


class PurchasabilityV2CompetitorTrace(BaseModel):
    decision_group: str | None = None
    probability_subgroup: str | None = None
    competitors_considered: list[str] = Field(default_factory=list)
    best_competitor_rating_market: str | None = None
    best_competitor_rating: float | None = None
    best_competitor_edge_market: str | None = None
    best_competitor_edge_pct: float | None = None
    best_competitor_probability_market: str | None = None
    best_competitor_probability: float | None = None
    opposite_selection: str | None = None
    opposite_fair_book_probability: float | None = None
    draw_opposite_trace: dict[str, Any] | None = None


class PurchasabilityV2Phase2Component(BaseModel):
    raw_value: float | None = None
    normalized_value: float | None = None
    configured_weight: float | None = None
    applied_weight: float | None = None
    contribution: float | None = None
    status: str | None = None
    normalization: PurchasabilityV2NormTrace | None = None
    best_competitor_market: str | None = None
    selected_value: float | None = None
    best_competitor_value: float | None = None


class PurchasabilityV2Phase2Quality(BaseModel):
    score: float | None = None
    status: PurchasabilityV2Status | str = "unavailable"
    configured_weights: dict[str, float] = Field(default_factory=dict)
    applied_weights: dict[str, float] = Field(default_factory=dict)
    coverage_ratio: float | None = None
    available_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    minimum_coverage_met: bool | None = None
    weight_policy: dict[str, Any] = Field(
        default_factory=lambda: {
            "kind": "initial_research_weights",
            "empirically_promoted": False,
            "label": "not_empirically_promoted",
        }
    )
    components: dict[str, Any] = Field(default_factory=dict)
    competitor_trace: PurchasabilityV2CompetitorTrace | dict[str, Any] = Field(
        default_factory=dict
    )
    reason_codes: list[str] = Field(default_factory=list)


class PurchasabilityV2PositiveValueGate(BaseModel):
    status: GateStatus | str = "unavailable"
    reason_codes: list[str] = Field(default_factory=list)
    edge_available: bool | None = None
    edge_positive: bool | None = None
    vantaggio_available: bool | None = None
    vantaggio_positive: bool | None = None
    reading: str | None = None


class PurchasabilityV2NormalizationProfileMeta(BaseModel):
    version: str | None = None
    hash: str | None = None
    cutoff: str | None = None
    summary: dict[str, Any] | None = None


class PurchasabilityV2Item(BaseModel):
    candidate_version: str = PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
    candidate_name: str = PURCHASABILITY_DECISION_V2_CANDIDATE_NAME
    contract_version: str = PURCHASABILITY_V2_CONTRACT_VERSION
    feature_version: str = PURCHASABILITY_V2_FEATURE_VERSION
    status: PurchasabilityV2Status | str = "unavailable"
    calculation_quality: CalculationQuality | str | None = None
    score: int | None = None
    raw_score: float | None = None
    raw_pre_gate_score: float | None = None
    class_: PurchasabilityClass | str | None = Field(default=None, alias="class")
    reading: str | None = None
    market_key: str
    selection: str | None = None
    phase_1_value: PurchasabilityV2Phase1Value | dict[str, Any] = Field(
        default_factory=dict
    )
    phase_2_quality: PurchasabilityV2Phase2Quality | dict[str, Any] = Field(
        default_factory=dict
    )
    positive_value_gate: PurchasabilityV2PositiveValueGate | dict[str, Any] = Field(
        default_factory=dict
    )
    normalization_profile: PurchasabilityV2NormalizationProfileMeta | dict[
        str, Any
    ] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class PurchasabilityV2CompactItem(BaseModel):
    market_key: str
    selection: str | None = None
    status: PurchasabilityV2Status | str = "unavailable"
    calculation_quality: CalculationQuality | str | None = None
    score: int | None = None
    raw_score: float | None = None
    raw_pre_gate_score: float | None = None
    class_: PurchasabilityClass | str | None = Field(default=None, alias="class")
    reading: str | None = None
    phase_1_score: float | None = None
    phase_2_score: float | None = None
    positive_value_gate: dict[str, Any] = Field(default_factory=dict)
    configured_weights_phase_1: dict[str, float] = Field(default_factory=dict)
    applied_weights_phase_1: dict[str, float] = Field(default_factory=dict)
    coverage_ratio_phase_1: float | None = None
    configured_weights_phase_2: dict[str, float] = Field(default_factory=dict)
    applied_weights_phase_2: dict[str, float] = Field(default_factory=dict)
    coverage_ratio_phase_2: float | None = None
    raw_components: dict[str, Any] = Field(default_factory=dict)
    normalized_components: dict[str, Any] = Field(default_factory=dict)
    best_competitor_keys: dict[str, Any] = Field(default_factory=dict)
    opposite_selection: str | None = None
    normalization_profile_version: str | None = None
    normalization_profile_hash: str | None = None
    reason_codes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PurchasabilityV2Snapshot(BaseModel):
    snapshot_version: str = PURCHASABILITY_V2_SNAPSHOT_VERSION
    contract_version: str = PURCHASABILITY_V2_CONTRACT_VERSION
    feature_version: str = PURCHASABILITY_V2_FEATURE_VERSION
    candidate_version: str = PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION
    candidate_name: str = PURCHASABILITY_DECISION_V2_CANDIDATE_NAME
    registry_status: str = PURCHASABILITY_V2_REGISTRY_STATUS
    status: Literal["ok", "partial", "unavailable"] | str = "unavailable"
    items: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    normalization_profile_version: str | None = None
    normalization_profile_hash: str | None = None
    normalization_profile_cutoff: str | None = None
    normalization_profile_summary: dict[str, Any] | None = None
    full_candidate_payload_sha256: str | None = None
    source_snapshot_at: str | None = None
    source_snapshot_verified: bool | None = None
    source_snapshot_before_kickoff: bool | None = None
    source_mode: str | None = None
    pre_match_only: bool = True
    contains_post_match_fields: bool = False
    signals_integration: bool = False
    warnings: list[str] = Field(default_factory=list)


class PurchasabilityComparisonMarketItem(BaseModel):
    v1_1_score: int | None = None
    v2_score: int | None = None
    delta_v2_minus_v1_1: int | None = None
    comparison_status: Literal["available", "partial", "unavailable"] | str = (
        "unavailable"
    )


class PurchasabilityComparison(BaseModel):
    items: dict[str, PurchasabilityComparisonMarketItem | dict[str, Any]] = Field(
        default_factory=dict
    )
