"""API pubblica monitoraggio giocate tracciate."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.tracked_pick_results_refresh_service import TrackedPickResultsRefreshService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/betting-picks", tags=["betting-picks"])


@router.get("/serie-a/{season}/tracked", response_model=None)
def list_tracked_betting_picks(season: int, db: Session = Depends(get_db)):
    try:
        out = TrackedPickResultsRefreshService().list_tracked_payload(db, int(season))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list tracked picks DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)
