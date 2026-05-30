"""Debug read-only Backtest Engine (Step C.1)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
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
