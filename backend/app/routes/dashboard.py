from fastapi import APIRouter, Depends, HTTPException
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
    try:
        data = svc.dashboard_serie_a(db, season)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    last = data.get("last_ingestion_run")
    cov = data["data_coverage"]
    return SerieADashboardResponse(
        league=LeagueDashboardBlock.model_validate(data["league"]),
        season=SeasonDashboardBlock.model_validate(data["season"]),
        teams_total=data["teams_total"],
        fixtures_total=data["fixtures_total"],
        fixtures_completed=data["fixtures_completed"],
        fixtures_scheduled=data["fixtures_scheduled"],
        fixtures_live_or_unknown=data["fixtures_live_or_unknown"],
        last_ingestion_run=IngestionRunSummary.model_validate(last) if last else None,
        data_coverage=DataCoverageBlock(
            teams_imported=bool(cov["teams_imported"]),
            fixtures_imported=bool(cov["fixtures_imported"]),
        ),
    )
