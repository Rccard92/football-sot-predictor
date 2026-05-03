from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dashboard import IngestionRunSummary, SerieADashboardResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/serie-a/{season}", response_model=SerieADashboardResponse)
def serie_a_dashboard(season: int, db: Session = Depends(get_db)) -> SerieADashboardResponse:
    svc = IngestionService()
    try:
        data = svc.dashboard_serie_a(db, season)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    last = data.get("last_ingestion_run")
    return SerieADashboardResponse(
        season=data["season"],
        league_api_id=data["league_api_id"],
        fixtures_total=data["fixtures_total"],
        fixtures_completed=data["fixtures_completed"],
        fixtures_with_team_stats=data["fixtures_with_team_stats"],
        fixtures_with_player_stats=data["fixtures_with_player_stats"],
        fixtures_with_lineups=data["fixtures_with_lineups"],
        coverage_team_stats_pct=data["coverage_team_stats_pct"],
        coverage_player_stats_pct=data["coverage_player_stats_pct"],
        coverage_lineups_pct=data["coverage_lineups_pct"],
        last_ingestion_run=IngestionRunSummary.model_validate(last) if last else None,
    )
