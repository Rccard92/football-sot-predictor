import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.player_sot_profile_service import PlayerSotProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/features/player-sot-profiles", tags=["player-sot-profiles"])


@router.post("/serie-a/{season}/build", response_model=None)
def build_player_sot_profiles_serie_a(season: int, db: Session = Depends(get_db)):
    svc = PlayerSotProfileService()
    try:
        summary = svc.build_for_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("build player_sot_profiles: DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    if summary.get("status") == "error":
        return JSONResponse(status_code=400, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/summary", response_model=None)
def player_sot_profiles_summary(season: int, db: Session = Depends(get_db)):
    svc = PlayerSotProfileService()
    try:
        return jsonable_encoder(svc.summary(db, season))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("player_sot_profiles summary: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
