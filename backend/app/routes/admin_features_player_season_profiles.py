"""Build profili stagionali Player DB (da player_match_stats)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.player_data.profile_builder import build_serie_a_player_season_profiles

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/features/player-season-profiles",
    tags=["admin-features-player-season-profiles"],
)


@router.post("/serie-a/{season}/build", response_model=None)
def build_player_season_profiles_serie_a(season: int, db: Session = Depends(get_db)):
    try:
        summary = build_serie_a_player_season_profiles(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("build player_season_profiles: DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    if summary.get("status") == "error":
        return JSONResponse(status_code=400, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)
