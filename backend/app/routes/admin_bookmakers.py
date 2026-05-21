"""Admin: discovery bookmakers API-Sports."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings, sportapi_configured
from app.core.database import get_db
from app.schemas.bookmakers import SportApiOddsDiscoveryBody
from app.services.api_football_client import ApiFootballError
from app.services.odds_bookmakers_sync_service import OddsBookmakersSyncService
from app.services.sportapi.sportapi_client import SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_odds_discovery_service import SportApiOddsDiscoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bookmakers", tags=["admin-bookmakers"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


@router.get("", response_model=None)
def list_bookmakers(db: Session = Depends(get_db)):
    try:
        out = OddsBookmakersSyncService().list_payload(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("list bookmakers DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(out)


@router.post("/sync", response_model=None)
def sync_bookmakers(db: Session = Depends(get_db)):
    _require_api_football_key()
    try:
        out = OddsBookmakersSyncService().sync_from_api(db)
    except ApiFootballError as exc:
        logger.warning("sync bookmakers API failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sync bookmakers DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync bookmakers failed")
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc
    return jsonable_encoder(out)


@router.post("/sportapi/odds-discovery", response_model=None)
def sportapi_odds_discovery(
    body: SportApiOddsDiscoveryBody,
    db: Session = Depends(get_db),
):
    if not sportapi_configured():
        raise HTTPException(
            status_code=400,
            detail="SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
        )
    if body.fixture_id is None and body.api_fixture_id is None and body.sportapi_event_id is None:
        raise HTTPException(
            status_code=400,
            detail="Specificare fixture_id, api_fixture_id o sportapi_event_id",
        )
    try:
        out = SportApiOddsDiscoveryService().discover(
            db,
            fixture_id=body.fixture_id,
            api_fixture_id=body.api_fixture_id,
            sportapi_event_id=body.sportapi_event_id,
            provider_id=int(body.provider_id),
            save_snapshot=bool(body.save_snapshot),
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi odds discovery DB error")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if out.get("status") == "error":
        msg = str(out.get("message") or "Errore discovery SportAPI")
        code = 400 if "Mapping" in msg or "Fixture" in msg else 502
        raise HTTPException(status_code=code, detail=msg)

    return jsonable_encoder(out)
