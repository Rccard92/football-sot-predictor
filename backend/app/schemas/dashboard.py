from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IngestionRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    records_processed: int
    error_message: str | None
    meta: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeagueDashboardBlock(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    api_league_id: int
    name: str
    country: str | None
    logo_url: str | None


class SeasonDashboardBlock(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    league_id: int
    year: int
    label: str | None
    is_current: bool


class DataCoverageBlock(BaseModel):
    teams_imported: bool
    fixtures_imported: bool


class SerieADashboardResponse(BaseModel):
    league: LeagueDashboardBlock | None
    season: SeasonDashboardBlock | None
    teams_total: int
    fixtures_total: int
    fixtures_completed: int
    fixtures_scheduled: int
    fixtures_live_or_unknown: int
    fixtures_with_team_stats: int
    team_stats_rows_total: int
    team_stats_coverage_pct: float
    sot_feature_rows_total: int
    sot_feature_expected_rows: int
    sot_feature_coverage_pct: float
    sot_predictions_total: int
    sot_predictions_expected: int
    sot_predictions_coverage_pct: float
    avg_expected_sot: float
    avg_prediction_confidence: float
    last_ingestion_run: IngestionRunSummary | None
    data_coverage: DataCoverageBlock
