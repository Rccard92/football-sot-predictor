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
    fixtures_with_player_stats: int = 0
    player_stats_rows_total: int = 0
    player_stats_coverage_pct: float = 0.0
    fixtures_with_lineups: int = 0
    lineups_rows_total: int = 0
    lineups_coverage_pct: float = 0.0
    players_profiled_total: int = 0
    player_profiles_total: int = 0
    player_profiles_sot_data_suspicious: bool = False
    availability_events_total: int = 0
    sot_feature_rows_total: int
    sot_feature_expected_rows: int
    sot_feature_coverage_pct: float
    sot_predictions_total: int
    sot_predictions_expected: int
    sot_predictions_coverage_pct: float
    avg_expected_sot: float
    avg_prediction_confidence: float
    sot_backtests_total: int
    sot_backtests_expected: int
    sot_backtest_coverage_pct: float
    sot_backtest_mae: float
    sot_backtest_rmse: float
    sot_backtest_avg_expected_sot: float
    sot_backtest_avg_actual_sot: float
    upcoming_fixtures_total: int = 0
    upcoming_sot_feature_rows_total: int = 0
    upcoming_sot_predictions_total: int = 0
    standings_snapshot_available: bool = False
    standings_snapshot_at: datetime | None = None
    next_round: str | None = None
    v02_predictions_upcoming: int = 0
    v02_avg_total_adjustment: float = 0.0
    v02_avg_player_adjustment: float = 0.0
    v02_avg_h2h_adjustment: float = 0.0
    v02_avg_motivation_adjustment: float = 0.0
    v02_matches_with_context_warning: int = 0
    last_ingestion_run: IngestionRunSummary | None
    data_coverage: DataCoverageBlock
