import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.standings import LatestStandingsResponse
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["standings"])


@router.get("/standings/serie-a/{season}/latest", response_model=LatestStandingsResponse)
def get_latest_standings(
    season: int,
    db: Session = Depends(get_db),
) -> LatestStandingsResponse:
    svc = IngestionService()
    try:
        payload = svc.latest_standings_for_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("latest standings: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return LatestStandingsResponse.model_validate(payload)


