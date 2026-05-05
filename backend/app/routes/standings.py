import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.standings import LatestStandingsResponse
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["standings"])


@router.get("/standings/serie-a/{season}/latest", response_model=LatestStandingsResponse)
def get_latest_standings(
    season: int,
    db: Session = Depends(get_db),
) -> LatestStandingsResponse:
    svc = IngestionService()
    try:
        payload = svc.latest_standings_for_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("latest standings: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    return LatestStandingsResponse.model_validate(payload)


@router.post("/admin/ingest/serie-a/{season}/standings", response_model=None)
def ingest_standings(
    season: int,
    db: Session = Depends(get_db),
):
    svc = IngestionService()
    try:
        run = svc.ingest_serie_a_standings(db, season)
        if run.status != "success":
            payload = {
                "status": "error",
                "failed_step": "save_standings_snapshot_entries",
                "message": run.error_message or "Standings ingestion failed.",
                "errors": [{"message": run.error_message or "unknown_error"}],
                "records_processed": int(run.records_processed or 0),
                "ingestion_run_id": run.id,
            }
            return JSONResponse(status_code=502, content=jsonable_encoder(payload))
        return jsonable_encoder(
            {
                "status": "success",
                "message": "Standings ingestion completed.",
                "errors": [],
                "failed_step": None,
                "records_processed": int(run.records_processed or 0),
                "ingestion_run_id": run.id,
            },
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("standings ingest: errore database")
        payload = {
            "status": "error",
            "failed_step": "database_operation",
            "message": "Database non disponibile o schema non aggiornato.",
            "errors": [{"message": str(exc)}],
        }
        return JSONResponse(status_code=503, content=jsonable_encoder(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("standings ingest: errore inatteso")
        payload = {
            "status": "error",
            "failed_step": "ingest_serie_a_standings",
            "message": "Errore inatteso durante ingestion standings.",
            "errors": [{"message": str(exc)}],
        }
        return JSONResponse(status_code=500, content=jsonable_encoder(payload))


