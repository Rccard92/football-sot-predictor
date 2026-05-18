"""Admin debug: summary availability stagione."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.availability.availability_debug import build_season_availability_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug", tags=["admin-debug"])


@router.get("/serie-a/{season}/availability-summary", response_model=None)
def admin_debug_availability_summary(
    season: int,
    db: Session = Depends(get_db),
):
    try:
        payload = build_season_availability_summary(db, int(season))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("availability-summary: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "season": int(season),
                },
            ),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=jsonable_encoder({"status": "error", "message": str(exc), "season": int(season)}),
        )
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))
