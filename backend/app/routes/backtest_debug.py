"""Debug read-only Backtest Engine (Step C.1 + D)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.point_in_time_context_service import PointInTimeContextService
from app.services.backtest_health_service import BacktestHealthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/debug", tags=["backtest-debug"])


@router.get("/health")
def backtest_debug_health(db: Session = Depends(get_db)):
    svc = BacktestHealthService()
    try:
        payload = svc.get_health(db)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest debug health: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/fixtures")
def backtest_debug_fixtures(
    competition_id: int = Query(...),
    season_year: int | None = Query(default=None),
    status: str = Query(default="finished"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    round_contains: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    svc = BacktestFixtureDebugService()
    try:
        payload = svc.list_candidate_fixtures(
            db,
            competition_id=competition_id,
            season_year=season_year,
            status=status,
            limit=limit,
            offset=offset,
            round_contains=round_contains,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest debug fixtures: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/point-in-time-context")
def backtest_debug_point_in_time_context(
    competition_id: int = Query(...),
    fixture_id: int = Query(...),
    market_key: str = Query(default="shots_on_target"),
    mode: str = Query(default="pre_lineup"),
    db: Session = Depends(get_db),
):
    svc = PointInTimeContextService()
    try:
        payload = svc.build_sot_context(
            db,
            competition_id=competition_id,
            fixture_id=fixture_id,
            mode=mode,
            market_key=market_key,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest point-in-time context: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)
