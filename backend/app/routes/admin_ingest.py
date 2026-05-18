import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import IngestionRun
from app.schemas.ingestion import IngestionRunRead
from app.services.ingestion_service import IngestionService
from app.services.player_data.orchestrator import run_player_db_update
from app.services.player_data.player_match_stats_ingestion import ingest_serie_a_player_match_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ingest", tags=["admin-ingest"])

SCHEMA_ERROR_BODY: dict = {
    "status": "error",
    "message": "Database schema not initialized. Run alembic upgrade head.",
}


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


def _any_failed(runs: list[IngestionRun]) -> bool:
    return any(r.status == "failed" for r in runs)


def _runs_to_jsonable(runs: list[IngestionRun]) -> list[dict]:
    return [IngestionRunRead.model_validate(r).model_dump() for r in runs]


@router.post("/serie-a/{season}/bootstrap", response_model=None)
def admin_bootstrap_serie_a(
    season: int,
    db: Session = Depends(get_db),
):
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

    runs_payload = _runs_to_jsonable(runs)

    if _any_failed(runs):
        failed = next((r for r in reversed(runs) if r.status == "failed"), None)
        failed_step = (failed.meta or {}).get("step") if failed and failed.meta else "unknown"
        message = (failed.error_message if failed and failed.error_message else None) or (
            "Uno o più step di bootstrap sono falliti"
        )
        body = {
            "status": "error",
            "failed_step": failed_step,
            "message": message,
            "partial_result": {"runs": runs_payload},
        }
        return JSONResponse(status_code=502, content=jsonable_encoder(body))

    return jsonable_encoder({"runs": runs_payload})


@router.post("/serie-a/{season}/team-stats", response_model=None)
def admin_ingest_serie_a_team_stats(
    season: int,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = IngestionService()
    try:
        summary = svc.sync_serie_a_team_stats_admin(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("team-stats: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "detail": str(exc),
                },
            ),
        )
    except Exception as exc:
        logger.exception("team-stats: errore imprevisto")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": str(exc),
                },
            ),
        )

    if summary.get("status") == "error":
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.post("/serie-a/{season}/player-match-stats", response_model=None)
def admin_ingest_serie_a_player_match_stats(
    season: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    try:
        payload = ingest_serie_a_player_match_stats(db, season, force=force)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("player-match-stats: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.get("status") == "error":
        return JSONResponse(status_code=502, content=jsonable_encoder(payload))
    return jsonable_encoder(payload)


@router.post("/serie-a/{season}/player-db", response_model=None)
def admin_ingest_serie_a_player_db(
    season: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    try:
        payload = run_player_db_update(db, season, force=force)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("player-db: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stats_run = payload.get("fixture_player_stats_ingestion") or {}
    if stats_run.get("status") == "failed":
        return JSONResponse(status_code=502, content=jsonable_encoder(payload))
    prof = payload.get("profiles") or {}
    if prof.get("status") == "error":
        return JSONResponse(status_code=502, content=jsonable_encoder(payload))
    return jsonable_encoder(payload)


@router.post("/serie-a/{season}/player-stats", response_model=None)
def admin_ingest_serie_a_player_stats(
    season: int,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = IngestionService()
    try:
        run = svc.ingest_serie_a_player_stats(db, season, run_source="serie_a_player_stats")
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("player-stats: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    if run.status == "failed":
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(IngestionRunRead.model_validate(run).model_dump()),
        )
    return jsonable_encoder(IngestionRunRead.model_validate(run).model_dump())


@router.post("/serie-a/{season}/lineups", response_model=None)
def admin_ingest_serie_a_lineups(
    season: int,
    fixture_id: int | None = Query(None),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    from app.services.lineups.lineup_ingestion import ingest_serie_a_lineups

    try:
        summary = ingest_serie_a_lineups(
            db,
            int(season),
            fixture_id=fixture_id,
            force=force,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("lineups: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if summary.get("status") == "error":
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.post("/serie-a/{season}/availability", response_model=None)
def admin_ingest_serie_a_availability(
    season: int,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = IngestionService()
    try:
        run = svc.ingest_serie_a_availability(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("availability: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    payload = IngestionRunRead.model_validate(run).model_dump()
    if run.status == "failed":
        return JSONResponse(status_code=502, content=jsonable_encoder(payload))
    return jsonable_encoder(payload)


@router.post("/serie-a/{season}/standings", response_model=None)
def admin_ingest_serie_a_standings(
    season: int,
    db: Session = Depends(get_db),
):
    _require_api_football_key()
    svc = IngestionService()
    try:
        run = svc.ingest_serie_a_standings(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("standings: errore database")
        raise HTTPException(status_code=503, detail="Database error") from exc
    payload = IngestionRunRead.model_validate(run).model_dump()
    if run.status == "failed":
        return JSONResponse(status_code=502, content=jsonable_encoder(payload))
    return jsonable_encoder(payload)


@router.get("/runs", response_model=None)
def admin_list_ingestion_runs(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        rows = db.scalars(
            select(IngestionRun).order_by(
                IngestionRun.started_at.desc().nulls_last(),
                IngestionRun.id.desc(),
            ).limit(limit),
        ).all()
        runs_out = [IngestionRunRead.model_validate(r).model_dump() for r in rows]
        return {"runs": runs_out, "total": len(runs_out)}
    except (ProgrammingError, OperationalError) as exc:
        logger.warning(
            "GET /api/admin/ingest/runs: errore SQLAlchemy (%s)",
            exc.__class__.__name__,
            exc_info=True,
        )
        return JSONResponse(status_code=503, content=SCHEMA_ERROR_BODY)
    except Exception:
        logger.exception("GET /api/admin/ingest/runs: errore imprevisto")
        return JSONResponse(status_code=503, content=SCHEMA_ERROR_BODY)
