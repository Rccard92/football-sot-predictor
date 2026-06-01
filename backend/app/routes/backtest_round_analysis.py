"""API analisi giornata persistente (Step I)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.backtest_round_analysis import RoundAnalysisAnalyzeRequest
from app.services.backtest.round_analysis_service import RoundAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/round-analysis", tags=["backtest-round-analysis"])


@router.post("/analyze")
def round_analysis_analyze(
    body: RoundAnalysisAnalyzeRequest,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.analyze(db, body)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST round-analysis/analyze: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder({"analysis": payload})


@router.get("")
def round_analysis_list(
    competition_id: int = Query(...),
    season_year: int = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.list_analyses(
            db,
            competition_id=competition_id,
            season_year=season_year,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)


@router.get("/{analysis_id}")
def round_analysis_detail(
    analysis_id: int,
    db: Session = Depends(get_db),
):
    svc = RoundAnalysisService()
    try:
        payload = svc.get_detail(db, analysis_id)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET round-analysis detail: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return jsonable_encoder(payload)
