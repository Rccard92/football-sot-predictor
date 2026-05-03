from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GeneratePredictionsBody(BaseModel):
    """Simulazione opzionale con linea over/under manuale (non quote automatiche)."""

    line_value: float | None = Field(
        default=None,
        description="Valore linea SOT per confronto (es. 4.5). Opzionale.",
    )


class GeneratePredictionsResponse(BaseModel):
    league_id: int
    season: int
    model_version: str
    rows_upserted: int


class TeamSotPredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fixture_id: int
    team_id: int
    model_version: str
    predicted_sot: float | None
    raw_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class FixturePredictionsResponse(BaseModel):
    fixture_id: int
    predictions: list[TeamSotPredictionRead]


class TeamPredictionsResponse(BaseModel):
    team_id: int
    predictions: list[TeamSotPredictionRead]
