import logging

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.competition_data_health_service import build_competition_data_health
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/data-health", tags=["admin-data-health"])


@router.get("/serie-a/{season}", response_model=None)
def admin_serie_a_data_health(season: int, db: Session = Depends(get_db)):
    svc = IngestionService()
    try:
        payload = svc.serie_a_team_stats_data_health(db, season)
        return jsonable_encoder(payload)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("data-health: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {"status": "error", "message": "Database error", "detail": str(exc)},
            ),
        )


@router.get("/serie-a/{season}/player-stats", response_model=None)
def admin_serie_a_player_stats_health(season: int, db: Session = Depends(get_db)):
    svc = IngestionService()
    try:
        return jsonable_encoder(svc.serie_a_player_stats_data_health(db, season))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("data-health player-stats: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder({"status": "error", "message": "Database error", "detail": str(exc)}),
        )


@router.get("/serie-a/{season}/lineups", response_model=None)
def admin_serie_a_lineups_health(season: int, db: Session = Depends(get_db)):
    svc = IngestionService()
    try:
        return jsonable_encoder(svc.serie_a_lineups_data_health(db, season))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("data-health lineups: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder({"status": "error", "message": "Database error", "detail": str(exc)}),
        )


@router.get("/competitions/{competition_id}", response_model=None)
def admin_competition_data_health(competition_id: int, db: Session = Depends(get_db)):
    try:
        return jsonable_encoder(build_competition_data_health(db, competition_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("data-health competition: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder({"status": "error", "message": "Database error", "detail": str(exc)}),
        )
