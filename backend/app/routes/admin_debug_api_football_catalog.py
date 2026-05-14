"""Scan catalogo campi diretti API-Football (admin / debug)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.api_football_client import ApiFootballError
from app.services.api_football_direct_catalog_scan import run_serie_a_direct_catalog_scan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug/api-football-catalog", tags=["admin-debug-api-football-catalog"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(status_code=503, detail="API_FOOTBALL_KEY non configurata sul server")


@router.post("/serie-a/{season}/scan", response_model=None)
def scan_serie_a_direct_catalog(season: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Interroga API-Football con parametri reali (Serie A), appiattisce le response,
    aggiorna la cache JSON dell'ultimo scan e restituisce il payload completo (inclusa diagnostica).
    """
    _require_api_football_key()
    try:
        return run_serie_a_direct_catalog_scan(db, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ApiFootballError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("scan_serie_a_direct_catalog")
        raise HTTPException(status_code=500, detail=f"Errore scan: {exc}") from exc
