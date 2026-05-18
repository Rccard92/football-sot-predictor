"""Admin debug: summary availability stagione."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.availability.availability_api_raw_list import build_availability_api_raw_list
from app.services.availability.availability_debug import build_season_availability_summary
from app.services.availability.availability_league import AvailabilityLeagueConfigError
from app.services.availability.availability_raw_check import build_availability_raw_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug", tags=["admin-debug"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


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


@router.get("/serie-a/{season}/availability-raw-check", response_model=None)
def admin_debug_availability_raw_check(
    season: int,
    fixture_id: int = Query(..., description="ID interno fixture"),
    player_search: str | None = Query(None, description="Substring nome giocatore, es. Rovella"),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    try:
        payload = build_availability_raw_check(
            db,
            int(season),
            int(fixture_id),
            player_search=player_search,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("availability-raw-check: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "season": int(season),
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": str(exc),
                    "season": int(season),
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("availability-raw-check: errore inatteso")
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": str(exc)[:500],
                    "season": int(season),
                    "fixture_id": int(fixture_id),
                },
            ),
        )
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/serie-a/{season}/availability-api-raw-list", response_model=None)
def admin_debug_availability_api_raw_list(
    season: int,
    team_id: int | None = Query(None, description="ID interno squadra"),
    fixture_id: int | None = Query(None, description="ID interno fixture"),
    date: str | None = Query(None, description="YYYY-MM-DD"),
    source: str = Query("injuries", description="Fonte API (default injuries)"),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    try:
        payload = build_availability_api_raw_list(
            db,
            int(season),
            team_id=team_id,
            fixture_id=fixture_id,
            date=date,
            source=source,
        )
    except AvailabilityLeagueConfigError as exc:
        return JSONResponse(
            status_code=400,
            content=jsonable_encoder(
                {
                    "status": "configuration_error",
                    "message": str(exc),
                    "season": int(season),
                },
            ),
        )
    except (OperationalError, ProgrammingError):
        logger.exception("availability-api-raw-list: errore database")
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
    except Exception as exc:  # noqa: BLE001
        logger.exception("availability-api-raw-list: errore inatteso")
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(
                {"status": "error", "message": str(exc)[:500], "season": int(season)},
            ),
        )
    if payload.get("status") == "configuration_error":
        return JSONResponse(status_code=400, content=jsonable_encoder(payload))
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))
