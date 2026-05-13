from typing import Literal

from pydantic import BaseModel


LegendSectionStatus = Literal["applicata", "solo_debug", "applicata_alla_lettura", "non_applicata"]


FrameworkImplementationStatus = Literal[
    "implementata",
    "parzialmente implementata",
    "solo debug",
    "da implementare",
    "non disponibile",
]

FrameworkMarketId = Literal[
    "tiri_in_porta",
    "tiri_totali",
    "corner",
    "cartellini",
    "falli",
    "goal_over_under",
]


class ModelLegendVariable(BaseModel):
    technical_key: str
    name: str
    description: str
    weight: float | None = None
    weight_label: str | None = None
    status: LegendSectionStatus
    impact: str
    interpretation: str


class ModelLegendSection(BaseModel):
    id: str
    title: str
    status: LegendSectionStatus
    description: str
    variables: list[ModelLegendVariable]


class ModelLegendResponse(BaseModel):
    model_version: str
    title: str
    description: str
    expected_sot_formula: str
    sections: list[ModelLegendSection]


class MatchAnalysisFrameworkVariable(BaseModel):
    area: str
    key: str
    name: str
    description: str
    impacted_markets: list[FrameworkMarketId]
    theoretical_weight: int
    weight_label: str
    data_source: str
    implementation_status: FrameworkImplementationStatus
    applied_now: bool
    notes: str | None = None
    applied_layer: str | None = None
    direct_formula_impact: bool | None = None
    decision_context_impact: bool | None = None
    applied_to_model_versions: list[str] | None = None
    application_role: str | None = None
    parent_component: str | None = None
    expected_in_debug: bool | None = None


class MatchAnalysisFrameworkArea(BaseModel):
    id: str
    title: str
    description: str
    variables: list[MatchAnalysisFrameworkVariable]


class MatchAnalysisMarketFramework(BaseModel):
    id: FrameworkMarketId
    title: str
    primary_variables: list[str]
    secondary_variables: list[str]
    warning_variables: list[str]
    less_relevant_variables: list[str]


class FutureEditableWeightsInfo(BaseModel):
    enabled_now: bool
    planned: bool
    description: str


class MatchAnalysisFrameworkResponse(BaseModel):
    title: str
    description: str
    version: str
    areas: list[MatchAnalysisFrameworkArea]
    market_frameworks: list[MatchAnalysisMarketFramework]
    future_editable_weights: FutureEditableWeightsInfo
