"""API Cecchino V3 (Fase 1). Stesse regole di accesso delle API di ricerca."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.cecchino_v3 import CecchinoV3MarketPrediction, CecchinoV3MatchPrediction
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_v3 import service

router = APIRouter(prefix="/admin/cecchino/v3", tags=["admin-cecchino-v3"])


def _raise(exc: CecchinoLabImportError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/runs")
def post_v3_run(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(status_code=202, content=jsonable_encoder(service.start_run(db)))
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.get("/runs/latest")
def get_latest_v3_run(db: Session = Depends(get_db)) -> JSONResponse:
    """Ultimo calcolo (anche in corso) e ultimo completato, per la pagina V3."""
    latest = service.latest_run(db)
    completed = service.latest_completed_run(db)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "latest": service.run_to_dict(latest) if latest else None,
                "completed": service.run_to_dict(completed) if completed else None,
            }
        )
    )


@router.get("/runs/{run_id}")
def get_v3_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(service.get_run(db, run_id)))
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.post("/runs/{run_id}/cancel")
def post_v3_run_cancel(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(service.cancel_run(db, run_id)))
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.get("/runs/{run_id}/matches")
def get_v3_run_matches(
    run_id: int,
    competition: str | None = Query(default=None),
    season_label: str | None = Query(default=None),
    team: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Previsioni partita per partita, con i 17 mercati, per il controllo a occhio."""
    q = select(CecchinoV3MatchPrediction).where(CecchinoV3MatchPrediction.run_id == run_id)
    if competition:
        q = q.where(CecchinoV3MatchPrediction.competition_name == competition)
    if season_label:
        q = q.where(CecchinoV3MatchPrediction.season_label == season_label)
    if team:
        q = q.where(
            (CecchinoV3MatchPrediction.home_team == team) | (CecchinoV3MatchPrediction.away_team == team)
        )
    rows = db.scalars(
        q.order_by(CecchinoV3MatchPrediction.kickoff_at.desc()).limit(limit).offset(offset)
    ).all()
    markets: dict[int, dict[str, dict[str, object]]] = {}
    if rows:
        for mk in db.scalars(
            select(CecchinoV3MarketPrediction).where(
                CecchinoV3MarketPrediction.match_prediction_id.in_([int(r.id) for r in rows])
            )
        ).all():
            markets.setdefault(int(mk.match_prediction_id), {})[mk.market_key] = {
                "probability": float(mk.probability),
                "won": mk.won,
            }
    items = [
        {
            "lab_match_id": int(r.lab_match_id),
            "competition": r.competition_name,
            "season_label": r.season_label,
            "kickoff_at": r.kickoff_at,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "score": f"{r.ft_home_goals}-{r.ft_away_goals}",
            "phase": r.phase,
            "eval_eligible": r.eval_eligible,
            "lambda_home": float(r.lambda_home),
            "lambda_away": float(r.lambda_away),
            "rho": float(r.rho),
            "home_evidence": float(r.home_evidence),
            "away_evidence": float(r.away_evidence),
            "markets": markets.get(int(r.id), {}),
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"items": items}))
