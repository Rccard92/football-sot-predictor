from typing import Literal

from pydantic import BaseModel


LegendSectionStatus = Literal["applicata", "solo_debug", "applicata_alla_lettura", "non_applicata"]


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
