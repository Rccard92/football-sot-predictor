"""Diagnostica read-only sul Player DB (registry, rose, copertura fps)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.player_data.player_db_health import player_match_db_health_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug", tags=["admin-debug-player-db"])


@router.get("/serie-a/{season}/player-db-summary", response_model=None)
def serie_a_player_db_summary(
    season: int,
    db: Session = Depends(get_db),
) -> dict:
    try:
        out = player_match_db_health_summary(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("player-db-summary DB error: %s", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    if out.get("status") == "error":
        raise HTTPException(status_code=400, detail=out.get("message", "Errore"))
    return out
