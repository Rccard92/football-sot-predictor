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


class SerieADashboardResponse(BaseModel):
    season: int
    league_api_id: int
    fixtures_total: int
    fixtures_completed: int
    fixtures_with_team_stats: int
    fixtures_with_player_stats: int
    fixtures_with_lineups: int
    coverage_team_stats_pct: float
    coverage_player_stats_pct: float
    coverage_lineups_pct: float
    last_ingestion_run: IngestionRunSummary | None
