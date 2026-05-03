import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION
from app.core.database import get_db
from app.schemas.backtest import (
    BacktestBySideListResponse,
    BacktestBySideRow,
    BacktestByTeamListResponse,
    BacktestByTeamRow,
    BacktestFixtureCompareItem,
    BacktestFixtureCompareResponse,
    BacktestNumericSummaryResponse,
    RunNumericBacktestBody,
    RunNumericBacktestResponse,
)
from app.services.sot_backtest_service import SotBacktestService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/sot", tags=["backtest"])


@router.post("/serie-a/{season}/run", response_model=None)
def run_numeric_backtest(
    season: int,
    db: Session = Depends(get_db),
    body: RunNumericBacktestBody = Body(default_factory=RunNumericBacktestBody),
):
    svc = SotBacktestService()
    try:
        summary = svc.run_numeric_backtest_admin(db, season, body.model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST run_sot_backtest: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("backtests_created_or_updated", 0) == 0:
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/summary", response_model=BacktestNumericSummaryResponse)
def numeric_backtest_summary(
    season: int,
    db: Session = Depends(get_db),
    model_version: str = BASELINE_SOT_MODEL_VERSION,
) -> BacktestNumericSummaryResponse:
    svc = SotBacktestService()
    try:
        data = svc.get_season_summary(db, season, model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET backtest summary: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return BacktestNumericSummaryResponse.model_validate(data)


@router.get("/serie-a/{season}/by-team", response_model=BacktestByTeamListResponse)
def numeric_backtest_by_team(
    season: int,
    db: Session = Depends(get_db),
    model_version: str = BASELINE_SOT_MODEL_VERSION,
) -> BacktestByTeamListResponse:
    svc = SotBacktestService()
    try:
        rows = svc.get_by_team(db, season, model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET backtest by-team: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return BacktestByTeamListResponse(
        season=season,
        model_version=model_version,
        teams=[BacktestByTeamRow.model_validate(r) for r in rows],
    )


@router.get("/serie-a/{season}/by-side", response_model=BacktestBySideListResponse)
def numeric_backtest_by_side(
    season: int,
    db: Session = Depends(get_db),
    model_version: str = BASELINE_SOT_MODEL_VERSION,
) -> BacktestBySideListResponse:
    svc = SotBacktestService()
    try:
        rows = svc.get_by_side(db, season, model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET backtest by-side: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return BacktestBySideListResponse(
        season=season,
        model_version=model_version,
        sides=[BacktestBySideRow.model_validate(r) for r in rows],
    )


@router.get("/fixture/{fixture_id}", response_model=BacktestFixtureCompareResponse)
def numeric_backtest_fixture(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str = BASELINE_SOT_MODEL_VERSION,
) -> BacktestFixtureCompareResponse:
    svc = SotBacktestService()
    try:
        rows = svc.get_fixture_comparison(db, fixture_id, model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET backtest fixture: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return BacktestFixtureCompareResponse(
        fixture_id=fixture_id,
        model_version=model_version,
        rows=[BacktestFixtureCompareItem.model_validate(r) for r in rows],
    )
