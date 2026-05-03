from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import IngestionRun
from app.schemas.ingestion import BootstrapResponse, IngestionRunRead, IngestionRunsResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


def _any_failed(runs: list[IngestionRun]) -> bool:
    return any(r.status == "failed" for r in runs)


@router.post("/serie-a/{season}/bootstrap", response_model=BootstrapResponse)
def bootstrap_serie_a(
    season: int,
    db: Session = Depends(get_db),
) -> BootstrapResponse:
    _require_api_football_key()
    svc = IngestionService()
    runs = svc.bootstrap_serie_a(db, season)
    if _any_failed(runs):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Uno o più step di bootstrap sono falliti",
                "runs": [IngestionRunRead.model_validate(r).model_dump() for r in runs],
            },
        )
    return BootstrapResponse(runs=[IngestionRunRead.model_validate(r) for r in runs])


@router.post("/serie-a/{season}/completed-fixtures/stats", response_model=IngestionRunRead)
def sync_completed_team_stats(
    season: int,
    db: Session = Depends(get_db),
) -> IngestionRun:
    _require_api_football_key()
    run = IngestionService().sync_completed_fixture_team_stats(db, season)
    if run.status == "failed":
        raise HTTPException(
            status_code=502,
            detail=IngestionRunRead.model_validate(run).model_dump(),
        )
    return run


@router.post("/serie-a/{season}/completed-fixtures/players", response_model=IngestionRunRead)
def sync_completed_player_stats(
    season: int,
    db: Session = Depends(get_db),
) -> IngestionRun:
    _require_api_football_key()
    run = IngestionService().sync_completed_fixture_player_stats(db, season)
    if run.status == "failed":
        raise HTTPException(
            status_code=502,
            detail=IngestionRunRead.model_validate(run).model_dump(),
        )
    return run


@router.post("/serie-a/{season}/completed-fixtures/lineups", response_model=IngestionRunRead)
def sync_completed_lineups(
    season: int,
    db: Session = Depends(get_db),
) -> IngestionRun:
    _require_api_football_key()
    run = IngestionService().sync_completed_fixture_lineups(db, season)
    if run.status == "failed":
        raise HTTPException(
            status_code=502,
            detail=IngestionRunRead.model_validate(run).model_dump(),
        )
    return run


@router.get("/runs", response_model=IngestionRunsResponse)
def list_ingestion_runs(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> IngestionRunsResponse:
    rows = db.scalars(
        select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit),
    ).all()
    return IngestionRunsResponse(runs=[IngestionRunRead.model_validate(r) for r in rows])
