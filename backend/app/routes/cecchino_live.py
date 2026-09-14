"""API registro previsioni live: consultazione pubblica, comandi con sessione admin."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_session import require_admin_session
from app.core.database import get_db
from app.models.cecchino_live_prediction import CecchinoLivePrediction
from app.services.cecchino_live.registry import record_predictions, settle_predictions
from app.services.cecchino_live.summary import live_summary

router = APIRouter(prefix="/cecchino-live", tags=["cecchino-live"])
admin_router = APIRouter(
    prefix="/admin/cecchino-live",
    tags=["admin-cecchino-live"],
    dependencies=[Depends(require_admin_session)],
)


def _to_dict(p: CecchinoLivePrediction) -> dict:
    return {
        "id": int(p.id),
        "today_fixture_id": int(p.today_fixture_id),
        "scan_date": p.scan_date.isoformat(),
        "kickoff": p.kickoff.isoformat() if p.kickoff else None,
        "league_name": p.league_name,
        "country_name": p.country_name,
        "home_team_name": p.home_team_name,
        "away_team_name": p.away_team_name,
        "model": p.model,
        "engine_version": p.engine_version,
        "status": p.status,
        "eligible": p.eligible,
        "frozen_at": p.frozen_at.isoformat() if p.frozen_at else None,
        "markets": p.markets_json,
        "modules": p.modules_json,
        "settled_at": p.settled_at.isoformat() if p.settled_at else None,
        "result": p.result_json,
    }


@router.get("/predictions")
def list_predictions(
    scan_date: date = Query(...),
    model: str | None = Query(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    q = select(CecchinoLivePrediction).where(CecchinoLivePrediction.scan_date == scan_date)
    if model:
        q = q.where(CecchinoLivePrediction.model == model)
    rows = db.scalars(q.order_by(CecchinoLivePrediction.kickoff, CecchinoLivePrediction.id)).all()
    return JSONResponse(content=jsonable_encoder({"items": [_to_dict(r) for r in rows]}))


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(live_summary(db)))


@admin_router.post("/record")
def record(scan_date: date = Query(...), db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(record_predictions(db, scan_date=scan_date)))


@admin_router.post("/settle")
def settle(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(settle_predictions(db)))
