from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GeneratePredictionsBody(BaseModel):
    """Opzionale: `line_value` non usato nello Step 5 (nessuna quota bookmaker)."""

    line_value: float | None = Field(
        default=None,
        description="Riservato per usi futuri. Ignorato da generate_for_season_admin.",
    )


class GeneratePredictionsResponseLegacy(BaseModel):
    league_id: int
    season: int
    model_version: str
    rows_upserted: int


class PredictionGenerateErrorItem(BaseModel):
    feature_id: int
    fixture_id: int
    team_id: int
    message: str


class GenerateSotPredictionsResponse(BaseModel):
    status: Literal["pending", "success", "error"]
    season: int
    model_version: str
    feature_rows_total: int = 0
    predictions_created_or_updated: int = 0
    errors: list[PredictionGenerateErrorItem] = Field(default_factory=list)
    ingestion_run_id: int | None = None
    message: str | None = None


class SotPredictionsSeasonSummaryResponse(BaseModel):
    season: int
    model_version: str
    feature_rows_total: int
    predictions_total: int
    coverage_pct: float
    avg_expected_sot: float
    min_expected_sot: float
    max_expected_sot: float
    avg_confidence_score: float


class FixtureSotPredictionItem(BaseModel):
    team_id: int
    team_name: str
    opponent_team_id: int
    opponent_name: str
    side: str
    expected_sot: float | None
    actual_sot: int | None
    confidence_score: int | None
    explanation: str


class FixturePredictionsEnrichedResponse(BaseModel):
    fixture_id: int
    predictions: list[FixtureSotPredictionItem]


class TeamSotPredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fixture_id: int
    team_id: int
    model_version: str
    predicted_sot: float | None
    actual_sot: int | None = None
    confidence_score: int | None = None
    explanation: str | None = None
    line_value: float | None = None
    over_probability: float | None = None
    under_probability: float | None = None
    recommendation: str | None = None
    raw_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class FixturePredictionsResponse(BaseModel):
    fixture_id: int
    predictions: list[TeamSotPredictionRead]


class TeamPredictionsResponse(BaseModel):
    team_id: int
    predictions: list[TeamSotPredictionRead]


class UpcomingSidePredictionBlock(BaseModel):
    expected_sot: float
    confidence_score: int
    confidence_label: str
    label: str
    simple_explanation: str
    technical_debug: dict[str, Any] = Field(default_factory=dict)


class UpcomingMatchTeamBlock(BaseModel):
    id: int
    name: str
    logo_url: str | None = None


class UpcomingMatchRow(BaseModel):
    fixture_id: int
    api_fixture_id: int
    round: str | None = None
    kickoff_at: datetime
    status_short: str
    home_team: UpcomingMatchTeamBlock
    away_team: UpcomingMatchTeamBlock
    home_prediction: UpcomingSidePredictionBlock | None = None
    away_prediction: UpcomingSidePredictionBlock | None = None


class UpcomingMatchesResponse(BaseModel):
    season: int
    round: str | None = None
    matches_count: int
    matches: list[UpcomingMatchRow]


class EvaluateSotLineBody(BaseModel):
    expected_sot: float = Field(..., ge=0, le=30)
    line_value: float = Field(..., ge=0, le=30)


class EvaluateSotLineResponse(BaseModel):
    expected_sot: float
    line_value: float
    gap: float
    suggestion: Literal["over", "under", "no_bet"]
    strength: Literal["forte", "interessante", "leggero", "neutro"]
    label: str
    explanation: str
