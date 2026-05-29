from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.competition_service import CompetitionService
from app.services.next_round_quick_report_service import build_next_round_quick_report_for_competition
from app.services.prediction_readiness import build_model_status_for_competition
from app.services.tracked_monitoring_dashboard_service import list_tracked_dashboard_for_competition

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
