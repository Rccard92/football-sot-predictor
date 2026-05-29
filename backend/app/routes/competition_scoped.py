from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.competition_service import CompetitionService
from app.services.next_round_quick_report_service import (
    build_next_round_quick_report_for_competition,
    build_upcoming_fixture_detail_for_competition,
)
from app.services.prediction_readiness import build_model_status_for_competition, _safe_details
from app.services.tracked_monitoring_dashboard_service import list_tracked_dashboard_for_competition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/competitions", tags=["competitions-scoped"])


@router.get("/{competition_id}/model-status")
def competition_model_status(competition_id: int, db: Session = Depends(get_db)):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    payload, code = build_model_status_for_competition(db, comp)
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


@router.get("/{competition_id}/next-round/quick-report")
def competition_next_round_quick_report(
    competition_id: int,
    limit: int = Query(20, ge=1, le=100),
    only_next_round: bool = Query(True),
    model_version: str | None = Query(None),
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    payload = build_next_round_quick_report_for_competition(
        db,
        comp,
        limit=limit,
        only_next_round=only_next_round,
        model_version=model_version,
    )
    return jsonable_encoder(payload)


@router.get("/{competition_id}/betting-picks/tracked")
def competition_tracked_betting_picks(
    competition_id: int,
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    return jsonable_encoder(list_tracked_dashboard_for_competition(db, comp))


@router.get("/{competition_id}/predictions/sot/upcoming-fixture/{fixture_id}/detail")
def competition_upcoming_fixture_detail(
    competition_id: int,
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str | None = Query(None),
):
    """Dettaglio/audit singola fixture upcoming scoped per competition."""
    try:
        comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "competition_not_found",
                    "message": str(exc.detail),
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "load_competition",
                }
            ),
        )
    try:
        payload, code = build_upcoming_fixture_detail_for_competition(
            db,
            comp,
            int(fixture_id),
            model_version=model_version,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "competition fixture detail: DB error competition=%s fixture=%s",
            competition_id,
            fixture_id,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "database_error",
                    "message": "Database error",
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "build_payload",
                    "details": _safe_details(exc),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "competition fixture detail: errore inatteso competition=%s fixture=%s",
            competition_id,
            fixture_id,
        )
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "code": "unexpected_error",
                    "message": "Errore inatteso durante il caricamento del dettaglio.",
                    "competition_id": int(competition_id),
                    "fixture_id": int(fixture_id),
                    "step": "build_payload",
                    "details": _safe_details(exc),
                }
            ),
        )
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))
