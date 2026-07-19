"""Contratto tecnico Acquistabilità V1 Preview — FASE 2/5 feature layer.

Versione contratto: cecchino_purchasability_v1_preview_contract
Feature version: cecchino_purchasability_features_v1

Nessuna formula 0–100. score/class/reading restano null finché status=not_calculated.
Affidabilità storica ≠ Acquistabilità; non copia Rating; non somma KPI.
Fase 2 riusa cecchino_market_opposition e fair book condiviso.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PURCHASABILITY_PREVIEW_CONTRACT_VERSION = "cecchino_purchasability_v1_preview_contract"
PURCHASABILITY_FEATURE_VERSION = "cecchino_purchasability_features_v1"

PurchasabilityStatus = Literal[
    "not_calculated",
    "available",
    "partial",
    "unavailable",
]

FeatureStatus = Literal["ready", "partial", "unavailable"]

PurchasabilityClass = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
]

ContextHookStatus = Literal[
    "not_connected",
    "available_not_used",
    "unavailable",
]

FavouriteAlignment = Literal["aligned", "disagree", "partial", "unavailable"]

GapDirection = Literal["positive", "negative", "neutral", "unavailable"]

RATING_DEPENDENCY_METADATA: dict[str, Any] = {
    "rating_is_derived": True,
    "rating_direct_inputs": ["prob_cecchino", "vantaggio_prob", "edge_pct"],
    "score_acquisto_is_derived": True,
    "score_acquisto_direct_inputs": ["prob_cecchino", "edge_pct"],
    "double_counting_prevention_required": True,
}


class PurchasabilityPhase1ValueInputs(BaseModel):
    quota_book: float | None = None
    quota_cecchino: float | None = None
    prob_book: float | None = None
    prob_cecchino: float | None = None
    vantaggio_prob: float | None = None
    edge_pct: float | None = None
    score_acquisto: float | None = None
    rating: float | None = None
    rating_label: str | None = None
    row_status: str | None = None
    book_source: str | None = None
    cecchino_source: str | None = None


class PurchasabilityPhase1Value(BaseModel):
    status: PurchasabilityStatus = "not_calculated"
    score: float | None = None
    inputs: PurchasabilityPhase1ValueInputs = Field(
        default_factory=PurchasabilityPhase1ValueInputs
    )
    dependency_metadata: dict[str, Any] = Field(
        default_factory=lambda: dict(RATING_DEPENDENCY_METADATA)
    )


class PurchasabilityBookFavourite(BaseModel):
    selection: str | None = None
    implied_prob: float | None = None


class PurchasabilityModelFavourite(BaseModel):
    selection: str | None = None
    model_prob: float | None = None


class PurchasabilityComparatorEvidence(BaseModel):
    market_key: str | None = None
    quota_book: float | None = None
    quota_cecchino: float | None = None
    raw_book_probability: float | None = None
    fair_book_probability: float | None = None
    fair_book_probability_verified: bool | None = None
    model_probability_raw: float | None = None
    model_probability_context: float | None = None
    book_probability_gap_vs_selected: float | None = None
    model_probability_gap_vs_selected: float | None = None
    book_odds_gap_vs_selected: float | None = None
    availability_status: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class PurchasabilityPhase2Quality(BaseModel):
    status: PurchasabilityStatus = "not_calculated"
    score: float | None = None
    opposition_status: str | None = None
    unsupported_reason: str | None = None
    canonical_market_family: str | None = None
    period: str | None = None
    line: float | None = None
    comparator_selections: list[str] = Field(default_factory=list)
    complement_selection: str | None = None
    comparator_evidence: list[PurchasabilityComparatorEvidence] = Field(
        default_factory=list
    )
    strongest_comparator_selection: str | None = None
    strongest_comparator_book_probability: float | None = None
    strongest_comparator_model_probability: float | None = None
    opposition_pressure_book: float | None = None
    opposition_pressure_model: float | None = None
    favourite_context_basis: str | None = None
    book_favourite: PurchasabilityBookFavourite | None = None
    model_favourite: PurchasabilityModelFavourite | None = None
    favourite_alignment: FavouriteAlignment | None = None
    favourite_intensity_book: float | None = None
    favourite_intensity_model: float | None = None
    fair_book_probability: float | None = None
    model_context_probability: float | None = None
    model_book_gap: float | None = None
    absolute_model_book_gap: float | None = None
    gap_direction: GapDirection | None = None


class PurchasabilityContextHook(BaseModel):
    status: ContextHookStatus = "not_connected"
    source_version: str | None = None
    available: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)
    payload: dict[str, Any] | None = None


class PurchasabilityContextHooks(BaseModel):
    balance_v5: PurchasabilityContextHook = Field(
        default_factory=PurchasabilityContextHook
    )
    goal_intensity_v5: PurchasabilityContextHook = Field(
        default_factory=PurchasabilityContextHook
    )


class PurchasabilityDataQuality(BaseModel):
    source: str = "stored_kpi_panel_snapshot"
    today_fixture_id: int | None = None
    local_fixture_id: int | None = None
    provider_fixture_id: int | None = None
    competition_id: int | None = None
    scan_date: str | None = None
    kickoff: str | None = None
    snapshot_at: str | None = None
    snapshot_source: str | None = None
    snapshot_fidelity: str | None = None
    snapshot_timestamp_verified: bool | None = None
    snapshot_before_kickoff: bool | None = None
    pre_match_only: bool = True
    no_post_match_features: bool = True
    contains_settlement_fields: bool = False
    contains_result_fields: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class CecchinoPurchasabilityPreviewContract(BaseModel):
    """Contratto preview — score sempre null finché status=not_calculated."""

    version: str = PURCHASABILITY_PREVIEW_CONTRACT_VERSION
    feature_version: str = PURCHASABILITY_FEATURE_VERSION
    feature_status: FeatureStatus | None = None
    status: PurchasabilityStatus = "not_calculated"
    score: float | None = None
    class_: PurchasabilityClass | None = Field(default=None, alias="class")
    reading: str | None = None
    market_key: str | None = None
    selection: str | None = None
    phase_1_value: PurchasabilityPhase1Value = Field(
        default_factory=PurchasabilityPhase1Value
    )
    phase_2_quality: PurchasabilityPhase2Quality = Field(
        default_factory=PurchasabilityPhase2Quality
    )
    context_hooks: PurchasabilityContextHooks = Field(
        default_factory=PurchasabilityContextHooks
    )
    reason_codes: list[str] = Field(default_factory=list)
    data_quality: PurchasabilityDataQuality = Field(
        default_factory=PurchasabilityDataQuality
    )

    model_config = {"populate_by_name": True}


def build_purchasability_preview_not_calculated(
    *,
    market_key: str | None = None,
    selection: str | None = None,
) -> dict[str, Any]:
    """Factory: contratto valido senza formula né placeholder numerici."""
    contract = CecchinoPurchasabilityPreviewContract(
        version=PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
        feature_version=PURCHASABILITY_FEATURE_VERSION,
        feature_status=None,
        status="not_calculated",
        score=None,
        class_=None,
        reading=None,
        market_key=market_key,
        selection=selection or market_key,
        phase_1_value=PurchasabilityPhase1Value(
            status="not_calculated",
            score=None,
            inputs=PurchasabilityPhase1ValueInputs(),
            dependency_metadata=dict(RATING_DEPENDENCY_METADATA),
        ),
        phase_2_quality=PurchasabilityPhase2Quality(
            status="not_calculated",
            score=None,
        ),
        context_hooks=PurchasabilityContextHooks(
            balance_v5=PurchasabilityContextHook(status="not_connected"),
            goal_intensity_v5=PurchasabilityContextHook(status="not_connected"),
        ),
        reason_codes=["purchasability_score_formula_not_implemented"],
        data_quality=PurchasabilityDataQuality(
            pre_match_only=True,
            no_post_match_features=True,
            contains_settlement_fields=False,
            contains_result_fields=False,
        ),
    )
    return contract.model_dump(by_alias=True)
