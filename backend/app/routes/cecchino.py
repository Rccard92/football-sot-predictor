"""Route API Cecchino — modulo separato da SOT."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino import (
    CecchinoBookmakerSyncBody,
    CecchinoDebugCalculateBody,
    CecchinoRecalculateBody,
)
from app.services.cecchino.cecchino_bookmaker_odds_service import load_fixture_bookmaker_odds_payload
from app.services.cecchino.cecchino_bookmaker_sync_service import CecchinoBookmakerSyncService
from app.services.cecchino.cecchino_constants import CECCHINO_VERSION
from app.services.cecchino.cecchino_service import (
    build_fixture_detail,
    build_upcoming_list,
    debug_calculate_from_manual,
    recalculate_for_competition,
)
from app.services.competition_service import CompetitionService
from app.services.prediction_readiness import _validate_fixture_for_competition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/competitions", tags=["cecchino"])
admin_router = APIRouter(prefix="/admin", tags=["admin-cecchino"])


@router.get("/{competition_id}/cecchino/upcoming")
def cecchino_upcoming(
    competition_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    payload = build_upcoming_list(db, comp, limit=limit, recalculate=False)
    return jsonable_encoder(payload)


@router.get("/{competition_id}/cecchino/fixture/{fixture_id}")
def cecchino_fixture_detail(
    competition_id: int,
    fixture_id: int,
    recalculate: bool = Query(False),
    force_recalculate: bool = Query(False),
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    fx, err, code = _validate_fixture_for_competition(db, comp, fixture_id)
    if err is not None:
        return JSONResponse(status_code=code or 404, content=jsonable_encoder(err))
    assert fx is not None
    do_recalc = recalculate or force_recalculate
    payload = build_fixture_detail(db, comp, fx, recalculate=do_recalc)
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/competitions/{competition_id}/cecchino/recalculate")
def cecchino_recalculate(
    competition_id: int,
    body: CecchinoRecalculateBody | None = None,
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    req = body or CecchinoRecalculateBody()
    payload = recalculate_for_competition(
        db,
        comp,
        fixture_id=req.fixture_id,
        limit=req.limit,
    )
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/cecchino/debug/calculate")
def cecchino_debug_calculate(body: CecchinoDebugCalculateBody):
    data = body.model_dump()
    payload = debug_calculate_from_manual(data)
    return jsonable_encoder(payload)


@router.get("/{competition_id}/cecchino/fixture/{fixture_id}/bookmaker-odds")
def cecchino_fixture_bookmaker_odds(
    competition_id: int,
    fixture_id: int,
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    fx, err, code = _validate_fixture_for_competition(db, comp, fixture_id)
    if err is not None:
        return JSONResponse(status_code=code or 404, content=jsonable_encoder(err))
    assert fx is not None
    payload = load_fixture_bookmaker_odds_payload(
        db,
        competition_id=int(comp.id),
        fixture_id=int(fx.id),
    )
    return jsonable_encoder(payload)


@admin_router.post("/competitions/{competition_id}/cecchino/bookmakers/sync-next-round")
def cecchino_sync_bookmaker_odds(
    competition_id: int,
    body: CecchinoBookmakerSyncBody | None = None,
    db: Session = Depends(get_db),
):
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)
    req = body or CecchinoBookmakerSyncBody()
    payload = CecchinoBookmakerSyncService().sync(
        db,
        int(comp.id),
        fixture_id=req.fixture_id,
        bookmaker_ids=req.bookmaker_ids,
        markets=req.markets,
    )
    status_code = 200 if payload.get("status") == "success" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))
