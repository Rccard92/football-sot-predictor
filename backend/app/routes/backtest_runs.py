"""API Backtest Engine — run management (Step C, nessun runtime calcolo)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.backtest_runs import (
    BacktestRunCreateRequest,
    BacktestRunDetailResponse,
    BacktestRunFilters,
    BacktestRunListItem,
    BacktestRunListResponse,
    BacktestRunResponse,
)
from app.services.backtest_run_service import BacktestRunService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/runs", tags=["backtest-runs"])


@router.post("")
def create_backtest_run(
    body: BacktestRunCreateRequest,
    db: Session = Depends(get_db),
):
    svc = BacktestRunService()
    try:
        run = svc.create_run(db, body)
    except HTTPException:
        raise
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST backtest run: errore database")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database error") from exc
    logger.info(
        "backtest run created id=%s competition_id=%s market_key=%s algorithm=%s",
        run.id,
        run.competition_id,
        run.market_key,
        run.algorithm_version,
    )
    return jsonable_encoder(BacktestRunResponse.model_validate(run).model_dump())


@router.get("")
def list_backtest_runs(
    db: Session = Depends(get_db),
    competition_id: int | None = Query(None),
    season_year: int | None = Query(None),
    market_key: str | None = Query(None),
    algorithm_version: str | None = Query(None),
    mode: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = BacktestRunFilters(
        competition_id=competition_id,
        season_year=season_year,
        market_key=market_key,
        algorithm_version=algorithm_version,
        mode=mode,
        status=status,
        limit=limit,
        offset=offset,
    )
    svc = BacktestRunService()
    try:
        rows, total = svc.list_runs(db, filters)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest runs: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc

    items: list[BacktestRunListItem] = []
    for run, competition_name in rows:
        item = BacktestRunListItem.model_validate(run)
        item.competition_name = competition_name
        items.append(item)

    return jsonable_encoder(
        BacktestRunListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        ).model_dump(),
    )


@router.get("/{run_id}")
def get_backtest_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    svc = BacktestRunService()
    try:
        detail = svc.get_run(db, int(run_id))
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET backtest run id=%s: errore database", run_id)
        raise HTTPException(status_code=503, detail="Database error") from exc

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "backtest_run_not_found",
                "message": "Backtest run non trovata.",
                "run_id": int(run_id),
            },
        )

    payload = BacktestRunDetailResponse.model_validate(detail.run).model_dump()
    payload["competition_name"] = detail.competition_name
    payload["predictions_count"] = detail.predictions_count
    payload["picks_count"] = detail.picks_count
    payload["metrics_count"] = detail.metrics_count
    return jsonable_encoder(payload)
