"""API RUN V2.5: consultazione pubblica (solo metadati), comandi con sessione admin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.admin_session import require_admin_session
from app.core.database import get_db
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2.run_service import cancel_run_v2
from app.services.cecchino_v25.run_service import (
    get_run_v25,
    list_runs_v25,
    resume_run_v25,
    start_run_v25,
)

router = APIRouter(prefix="/cecchino-run-v25", tags=["cecchino-run-v25"])
admin_router = APIRouter(
    prefix="/admin/cecchino-run-v25",
    tags=["admin-cecchino-run-v25"],
    dependencies=[Depends(require_admin_session)],
)


def _error(exc: CecchinoLabImportError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": exc.code, "message": exc.message, "details": exc.details},
    )


@router.get("")
def list_runs(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder({"items": list_runs_v25(db)}))


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(get_run_v25(db, run_id)))
    except CecchinoLabImportError as exc:
        return _error(exc)


@admin_router.post("")
def start_run(body: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> JSONResponse:
    payload = body or {}
    try:
        result = start_run_v25(db, confirm=payload.get("confirm"), season=payload.get("season"))
    except CecchinoLabImportError as exc:
        return _error(exc)
    return JSONResponse(content=jsonable_encoder(result), status_code=202)


@admin_router.post("/{run_id}/resume")
def resume_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        result = resume_run_v25(db, run_id)
    except CecchinoLabImportError as exc:
        return _error(exc)
    return JSONResponse(content=jsonable_encoder(result), status_code=202)


@admin_router.post("/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        get_run_v25(db, run_id)
        result = cancel_run_v2(db, run_id)
    except CecchinoLabImportError as exc:
        return _error(exc)
    return JSONResponse(content=jsonable_encoder(result))
