"""Admin: refresh risultati tracked picks (API-Sports)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.api_football_client import ApiFootballError
from app.services.tracked_pick_results_refresh_service import TrackedPickResultsRefreshService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/betting-picks", tags=["admin-betting-picks"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


@router.post("/serie-a/{season}/refresh-results", response_model=None)
def refresh_tracked_pick_results(season: int, db: Session = Depends(get_db)):
    _require_api_football_key()
    try:
        out = TrackedPickResultsRefreshService().refresh_results(db, int(season))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("refresh tracked results DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ApiFootballError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return jsonable_encoder(out)
