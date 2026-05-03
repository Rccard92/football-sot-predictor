import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import IngestionRun
from app.schemas.ingestion import BootstrapResponse, IngestionRunRead, IngestionRunsResponse
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ingest", tags=["admin-ingest"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


def _any_failed(runs: list[IngestionRun]) -> bool:
    return any(r.status == "failed" for r in runs)


@router.post("/serie-a/{season}/bootstrap", response_model=BootstrapResponse)
def admin_bootstrap_serie_a(
    season: int,
    db: Session = Depends(get_db),
) -> BootstrapResponse:
    _require_api_football_key()
    svc = IngestionService()
    try:
        runs = svc.bootstrap_serie_a_admin(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("bootstrap: errore database (schema o connessione)")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire le migration Alembic (alembic upgrade head) su PostgreSQL.",
        ) from exc
    if _any_failed(runs):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Uno o più step di bootstrap sono falliti",
                "runs": [IngestionRunRead.model_validate(r).model_dump() for r in runs],
            },
        )
    return BootstrapResponse(runs=[IngestionRunRead.model_validate(r) for r in runs])


@router.get("/runs", response_model=IngestionRunsResponse)
def admin_list_ingestion_runs(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> IngestionRunsResponse:
    rows = db.scalars(
        select(IngestionRun).order_by(
            IngestionRun.started_at.desc().nulls_last(),
            IngestionRun.id.desc(),
        ).limit(limit),
    ).all()
    return IngestionRunsResponse(runs=[IngestionRunRead.model_validate(r) for r in rows])
