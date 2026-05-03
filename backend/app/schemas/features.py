from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TeamSotFeatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fixture_id: int
    team_id: int
    opponent_team_id: int | None = None
    side: str | None = None
    fixture_date: datetime | None = None
    season_avg_sot_for: float | None = None
    season_avg_sot_against: float | None = None
    home_away_avg_sot_for: float | None = None
    home_away_avg_sot_against: float | None = None
    last5_avg_sot_for: float | None = None
    last5_avg_sot_against: float | None = None
    last10_avg_sot_for: float | None = None
    last10_avg_sot_against: float | None = None
    opponent_season_avg_sot_conceded: float | None = None
    opponent_home_away_avg_sot_conceded: float | None = None
    opponent_last5_avg_sot_conceded: float | None = None
    rest_days: int | None = None
    actual_sot: int | None = None
    fallback_used: bool = False
    previous_matches_count: int | None = None
    opponent_previous_matches_count: int | None = None
    feature_set_version: str | None = None
    features: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class SotFeatureBuildErrorItem(BaseModel):
    fixture_id: int
    api_fixture_id: int
    team_id: int | None = None
    message: str


class SotFeatureBuildResponse(BaseModel):
    status: Literal["pending", "success", "error"]
    season: int
    fixtures_targeted: int = 0
    rows_upserted: int = 0
    errors: list[SotFeatureBuildErrorItem] = Field(default_factory=list)
    ingestion_run_id: int | None = None
    message: str | None = None


class SotFeatureSeasonSummaryResponse(BaseModel):
    season: int
    fixtures_completed: int
    expected_feature_rows: int
    feature_rows_total: int
    coverage_pct: float
    missing_feature_rows: int


class SotFixtureFeaturesResponse(BaseModel):
    fixture_id: int
    rows: list[TeamSotFeatureRead]
