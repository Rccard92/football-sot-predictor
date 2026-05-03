from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dashboard import (
    DataCoverageBlock,
    IngestionRunSummary,
    LeagueDashboardBlock,
    SeasonDashboardBlock,
    SerieADashboardResponse,
)
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/serie-a/{season}", response_model=SerieADashboardResponse)
def serie_a_dashboard(season: int, db: Session = Depends(get_db)) -> SerieADashboardResponse:
    svc = IngestionService()
    data = svc.dashboard_serie_a(db, season)

    last = data.get("last_ingestion_run")
    cov = data["data_coverage"]
    league = data.get("league")
    season_row = data.get("season")
    return SerieADashboardResponse(
        league=LeagueDashboardBlock.model_validate(league) if league is not None else None,
        season=SeasonDashboardBlock.model_validate(season_row) if season_row is not None else None,
        teams_total=data["teams_total"],
        fixtures_total=data["fixtures_total"],
        fixtures_completed=data["fixtures_completed"],
        fixtures_scheduled=data["fixtures_scheduled"],
        fixtures_live_or_unknown=data["fixtures_live_or_unknown"],
        fixtures_with_team_stats=data["fixtures_with_team_stats"],
        team_stats_rows_total=data["team_stats_rows_total"],
        team_stats_coverage_pct=float(data["team_stats_coverage_pct"]),
        last_ingestion_run=IngestionRunSummary.model_validate(last) if last else None,
        data_coverage=DataCoverageBlock(
            teams_imported=bool(cov["teams_imported"]),
            fixtures_imported=bool(cov["fixtures_imported"]),
        ),
    )
