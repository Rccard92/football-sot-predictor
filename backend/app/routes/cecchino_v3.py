"""API Cecchino V3: calcoli del motore, indici per partita e ricerca pattern."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_v3 import index_service, pattern_service, service

router = APIRouter(prefix="/admin/cecchino/v3", tags=["admin-cecchino-v3"])


def _raise(exc: CecchinoLabImportError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/runs")
def post_v3_run(phase: int = Query(default=4), db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(status_code=202, content=jsonable_encoder(service.start_run(db, phase=phase)))
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.get("/runs/latest")
def get_latest_v3_run(db: Session = Depends(get_db)) -> JSONResponse:
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


@router.get("/runs")
def get_v3_runs(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder({"items": service.list_completed_runs(db)}))


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


@router.post("/indices/runs")
def post_v3_index_run(
    source_run_id: int | None = Query(default=None), db: Session = Depends(get_db)
) -> JSONResponse:
    """Indici per partita dal modello di riferimento (o dal calcolo indicato)."""
    try:
        return JSONResponse(
            status_code=202, content=jsonable_encoder(index_service.start_index_run(db, source_run_id))
        )
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.get("/indices/runs/latest")
def get_v3_index_runs_latest(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(index_service.latest_index_runs(db)))


@router.post("/pattern/runs")
def post_v3_pattern_run(db: Session = Depends(get_db)) -> JSONResponse:
    """Ricerca pattern V3 (base dei pattern V3 della Master Pattern)."""
    try:
        return JSONResponse(status_code=202, content=jsonable_encoder(pattern_service.start_pattern_run(db)))
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.get("/pattern/runs/latest")
def get_v3_pattern_runs_latest(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(pattern_service.latest_pattern_runs(db)))
