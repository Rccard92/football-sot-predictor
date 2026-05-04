from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class UpcomingSotCalculationBreakdown(BaseModel):
    """Breakdown baseline v0.1: contributi = valore_usato × peso (da raw_json prediction)."""

    season_avg_sot_for: float
    season_avg_sot_for_weight: float = 0.30
    season_avg_sot_for_contribution: float
    season_avg_sot_for_fallback_used: bool = False
    season_avg_sot_for_fallback_note: str | None = None

    opponent_season_avg_sot_conceded: float
    opponent_season_avg_sot_conceded_weight: float = 0.25
    opponent_season_avg_sot_conceded_contribution: float
    opponent_season_avg_sot_conceded_fallback_used: bool = False
    opponent_season_avg_sot_conceded_fallback_note: str | None = None

    home_away_avg_sot_for: float
    home_away_avg_sot_for_weight: float = 0.15
    home_away_avg_sot_for_contribution: float
    home_away_avg_sot_for_fallback_used: bool = False
    home_away_avg_sot_for_fallback_note: str | None = None

    opponent_home_away_avg_sot_conceded: float
    opponent_home_away_avg_sot_conceded_weight: float = 0.10
    opponent_home_away_avg_sot_conceded_contribution: float
    opponent_home_away_avg_sot_conceded_fallback_used: bool = False
    opponent_home_away_avg_sot_conceded_fallback_note: str | None = None

    last5_avg_sot_for: float
    last5_avg_sot_for_weight: float = 0.10
    last5_avg_sot_for_contribution: float
    last5_avg_sot_for_fallback_used: bool = False
    last5_avg_sot_for_fallback_note: str | None = None

    opponent_last5_avg_sot_conceded: float
    opponent_last5_avg_sot_conceded_weight: float = 0.10
    opponent_last5_avg_sot_conceded_contribution: float
    opponent_last5_avg_sot_conceded_fallback_used: bool = False
    opponent_last5_avg_sot_conceded_fallback_note: str | None = None

    expected_sot_total: float


class UpcomingSidePredictionBlock(BaseModel):
    expected_sot: float
    confidence_score: int
    confidence_label: str
    data_quality_score: int
    data_quality_label: str
    prediction_confidence_score: int
    prediction_confidence_label: str
    label: str
    simple_explanation: str
    calculation_breakdown: UpcomingSotCalculationBreakdown | None = None


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
    total_expected_sot: float | None = None
    h2h_summary: dict[str, Any] | None = None
    player_impact_status: dict[str, Any] | None = None


class ModelLimitationsBlock(BaseModel):
    lineups_considered: bool = False
    injuries_considered: bool = False
    odds_automatically_imported: bool = False
    note: str


class UpcomingMatchesResponse(BaseModel):
    season: int
    round: str | None = None
    matches_count: int
    matches: list[UpcomingMatchRow]
    model_limitations: ModelLimitationsBlock


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


class EvaluateMatchSotLineBody(BaseModel):
    home_expected_sot: float = Field(..., ge=0, le=30)
    away_expected_sot: float = Field(..., ge=0, le=30)
    market_type: str = Field(default="match_total_sot")
    line_value: float = Field(..., ge=0, le=40)
    odds: float | None = Field(default=None)
    bookmaker: str = Field(..., min_length=1, max_length=120)

    @field_validator("odds")
    @classmethod
    def validate_odds(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if v <= 1.0 or v > 1000.0:
            raise ValueError("odds deve essere maggiore di 1.0 e al massimo 1000")
        return v


class EvaluateMatchSotLineResponse(BaseModel):
    market_type: str
    bookmaker: str
    line_value: float
    odds: float | None = None
    home_expected_sot: float
    away_expected_sot: float
    total_expected_sot: float
    gap: float
    suggestion: Literal["over", "under", "no_bet"]
    strength: Literal["forte", "interessante", "leggero", "neutro"]
    label: str
    implied_probability: float | None = None
    explanation: str
