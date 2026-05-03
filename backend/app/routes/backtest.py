from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import League, Season
from app.schemas.backtest import (
    BacktestByLineResponse,
    BacktestByTeamResponse,
    BacktestSummaryResponse,
    RunBacktestBody,
    RunBacktestResponse,
)
from app.services.backtest_service import BacktestService
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/backtest/sot", tags=["backtest"])


def _season_or_404(db: Session, season_year: int) -> Season:
    league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
    if league is None:
        raise HTTPException(status_code=404, detail="Lega Serie A non trovata")
    season = db.scalar(
        select(Season).where(Season.league_id == league.id, Season.year == season_year),
    )
    if season is None:
        raise HTTPException(status_code=404, detail=f"Stagione {season_year} non trovata")
    return season


@router.post("/serie-a/{season}/run", response_model=RunBacktestResponse)
def run_backtest(
    season: int,
    body: RunBacktestBody,
    db: Session = Depends(get_db),
) -> RunBacktestResponse:
    _season_or_404(db, season)
    svc = BacktestService()
    try:
        batch_id, n = svc.run_sot_backtest(
            db,
            season,
            body.model_version,
            body.default_lines,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return RunBacktestResponse(
        batch_id=batch_id,
        season=season,
        model_version=body.model_version,
        rows_written=n,
    )


@router.get("/serie-a/{season}/summary", response_model=BacktestSummaryResponse)
def backtest_summary(
    season: int,
    db: Session = Depends(get_db),
    batch_id: str | None = Query(default=None),
) -> BacktestSummaryResponse:
    s = _season_or_404(db, season)
    svc = BacktestService()
    bid = svc.resolve_batch_id(db, s.id, batch_id)
    if bid is None:
        raise HTTPException(status_code=404, detail="Nessun backtest trovato per questa stagione")
    rows = svc.load_batch_rows(db, s.id, bid)
    agg = svc.aggregate_summary(rows)
    by_side = svc.aggregate_by_side(rows)
    return BacktestSummaryResponse(
        batch_id=bid,
        season=season,
        mae=agg["mae"],
        rmse=agg["rmse"],
        hit_rate=agg["hit_rate"],
        no_bet_rate=agg["no_bet_rate"],
        total_predictions=agg["total_predictions"],
        total_line_evaluations=agg["total_line_evaluations"],
        error_by_side=by_side,
    )


@router.get("/serie-a/{season}/by-team", response_model=BacktestByTeamResponse)
def backtest_by_team(
    season: int,
    db: Session = Depends(get_db),
    batch_id: str | None = Query(default=None),
) -> BacktestByTeamResponse:
    s = _season_or_404(db, season)
    svc = BacktestService()
    bid = svc.resolve_batch_id(db, s.id, batch_id)
    if bid is None:
        raise HTTPException(status_code=404, detail="Nessun backtest trovato per questa stagione")
    rows = svc.load_batch_rows(db, s.id, bid)
    return BacktestByTeamResponse(
        batch_id=bid,
        season=season,
        error_by_team=svc.aggregate_by_team(rows),
    )


@router.get("/serie-a/{season}/by-line", response_model=BacktestByLineResponse)
def backtest_by_line(
    season: int,
    db: Session = Depends(get_db),
    batch_id: str | None = Query(default=None),
) -> BacktestByLineResponse:
    s = _season_or_404(db, season)
    svc = BacktestService()
    bid = svc.resolve_batch_id(db, s.id, batch_id)
    if bid is None:
        raise HTTPException(status_code=404, detail="Nessun backtest trovato per questa stagione")
    rows = svc.load_batch_rows(db, s.id, bid)
    return BacktestByLineResponse(
        batch_id=bid,
        season=season,
        error_by_line=svc.aggregate_by_line(rows),
    )
