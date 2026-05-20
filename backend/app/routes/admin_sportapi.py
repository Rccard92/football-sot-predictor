"""Admin/debug SportAPI RapidAPI — mapping e lineups (non usati nel modello)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import sportapi_configured
from app.core.database import get_db
from app.schemas.sportapi import SportApiMappingConfirmBody
from app.services.sportapi.sportapi_client import SportApiDisabledError
from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sportapi", tags=["admin-sportapi"])


def _fixture_not_found_message(payload: dict) -> str | None:
    msg = str(payload.get("message") or "")
    if payload.get("status") != "error":
        return None
    if msg == FIXTURE_NOT_FOUND_MSG or "non trovata" in msg.lower():
        return msg or FIXTURE_NOT_FOUND_MSG
    return None


def _require_sportapi_enabled() -> None:
    if not sportapi_configured():
        raise HTTPException(
            status_code=400,
            detail="SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
        )


@router.get("/debug/fixture/{fixture_id}", response_model=None)
def sportapi_debug_fixture_match(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Match debug: una sola chiamata scheduled-events per la data della fixture."""
    try:
        svc = SportApiMatchingService()
        payload = svc.debug_match_fixture(db, int(fixture_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi debug DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        return jsonable_encoder(
            {
                "status": "disabled",
                "message": str(exc),
                "fixture_id": int(fixture_id),
                "sportapi_enabled": False,
            },
        )

    not_found = _fixture_not_found_message(payload)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)
    return jsonable_encoder(payload)


@router.post("/mappings/{fixture_id}/confirm", response_model=None)
def sportapi_confirm_mapping(
    fixture_id: int,
    body: SportApiMappingConfirmBody,
    db: Session = Depends(get_db),
):
    _require_sportapi_enabled()
    if body.confidence_score is not None and body.confidence_score < 90:
        logger.info(
            "sportapi mapping confirm fixture=%s score=%s (manual override)",
            fixture_id,
            body.confidence_score,
        )
    try:
        out = SportApiLineupService().confirm_mapping(
            db,
            int(fixture_id),
            provider_event_id=body.provider_event_id,
            confidence_score=body.confidence_score,
            matched_by=body.matched_by or "admin_manual",
            raw_payload=body.raw_payload,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi confirm mapping DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    not_found = _fixture_not_found_message(out)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)
    return jsonable_encoder(out)


@router.post("/lineups/{fixture_id}/fetch", response_model=None)
def sportapi_fetch_lineups(
    fixture_id: int,
    db: Session = Depends(get_db),
):
    """Fetch lineups per event_id mappato (1 chiamata API)."""
    _require_sportapi_enabled()
    try:
        out = SportApiLineupService().fetch_and_persist_lineups(db, int(fixture_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi fetch lineups DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if out.get("status") == "error":
        msg = str(out.get("message") or "")
        not_found = _fixture_not_found_message(out)
        if not_found:
            raise HTTPException(status_code=404, detail=not_found)
        if "non trovato" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=502, detail=msg)
    return jsonable_encoder(out)


@router.get("/lineups/{fixture_id}", response_model=None)
def sportapi_get_lineups(
    fixture_id: int,
    include_raw: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        out = SportApiLineupService().get_stored_lineups(
            db,
            int(fixture_id),
            include_raw=include_raw,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("sportapi get lineups DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc

    not_found = _fixture_not_found_message(out)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)
    return jsonable_encoder(out)
