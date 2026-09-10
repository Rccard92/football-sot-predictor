"""API RUN V2 Cecchino Lab.

L'export viene sempre rigenerato dal DB al momento della richiesta: i file su
disco sono effimeri e non fanno parte del contratto.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.admin_session import AdminSession, require_admin_session
from app.core.database import get_db
from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2.export import (
    EXPORT_FILES,
    FILE_FULL,
    build_export_bundle,
)
from app.services.cecchino_data_lab.run_v2.run_service import (
    cancel_run_v2,
    list_runs_v2,
    resume_run_v2,
    run_v2_to_dict,
    start_run_v2,
)
from app.services.cecchino_data_lab.run_v2.preflight import run_v2_preflight

# Consultazione read-only (list/detail/preflight): pubblica — solo metadata
# aggregati (stato, progress, coverage, summary), nessuna riga raw/export.
# Control plane (start/resume/cancel) e download export/manifest: sessione admin.
# Il token di conferma nel body e' pubblico e non autorizza nulla.
router = APIRouter(
    prefix="/cecchino-run-v2",
    tags=["cecchino-run-v2"],
)
admin_router = APIRouter(
    prefix="/admin/cecchino-run-v2",
    tags=["admin-cecchino-run-v2"],
    dependencies=[Depends(require_admin_session)],
)
logger = logging.getLogger(__name__)

STREAM_CHUNK_BYTES = 1024 * 512


def _run_to_dict(run: CecchinoRunV2Run) -> dict[str, Any]:
    """Serializzazione condivisa con il service (include lo stato effettivo)."""
    return run_v2_to_dict(run)


def _error_response(exc: CecchinoLabImportError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@router.get("")
@admin_router.get("")
def list_runs(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder({"items": list_runs_v2(db)}))


@router.get("/preflight")
@admin_router.get("/preflight")
def preflight_run(
    season: str = Query(..., min_length=1, description="Stagione Lab, es. 2024/2025"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Read-only: match/competizioni disponibili per la stagione selezionata."""
    return JSONResponse(content=jsonable_encoder(run_v2_preflight(db, season_label=season)))


@router.get("/{run_id}")
@admin_router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_v2 {run_id} inesistente")
    return JSONResponse(content=jsonable_encoder(_run_to_dict(run)))


@admin_router.post("")
def start_run(body: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> JSONResponse:
    """Avvia una RUN V2 in background e risponde subito con run_id e stato."""
    payload = body or {}
    try:
        result = start_run_v2(
            db,
            confirm=payload.get("confirm"),
            season=payload.get("season"),
            season_label=payload.get("season_label"),
            max_matches=payload.get("max_matches"),
            pilot_strategy=payload.get("pilot_strategy"),
            eligible_per_competition=payload.get("eligible_per_competition"),
            background=True,
        )
    except CecchinoLabImportError as exc:
        return _error_response(exc)
    return JSONResponse(content=jsonable_encoder(result), status_code=202)


@admin_router.post("/{run_id}/resume")
def resume_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    """Riprende una RUN V2 dal checkpoint gia persistito sugli snapshot."""
    try:
        result = resume_run_v2(db, int(run_id), background=True)
    except CecchinoLabImportError as exc:
        return _error_response(exc)
    return JSONResponse(content=jsonable_encoder(result), status_code=202)


@admin_router.post("/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        result = cancel_run_v2(db, int(run_id))
    except CecchinoLabImportError as exc:
        return _error_response(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/{run_id}/export")
@admin_router.get("/{run_id}/export")
def export_run(
    run_id: int,
    file: str = Query(FILE_FULL, description=f"Uno fra: {', '.join(EXPORT_FILES)}"),
    db: Session = Depends(get_db),
    _admin: AdminSession = Depends(require_admin_session),
) -> StreamingResponse:
    """Rigenera gli artefatti dal DB e streamma il file richiesto."""
    if file not in EXPORT_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"file deve essere uno fra {', '.join(EXPORT_FILES)}",
        )
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_v2 {run_id} inesistente")

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"cecchino_run_v2_{run_id}_"))
    try:
        manifest = build_export_bundle(db, run_id=int(run_id), output_dir=tmp_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    target = Path(manifest["files"][file])
    media_type = "application/json" if file.endswith(".json") else "text/csv"

    def _iter_file() -> Iterator[bytes]:
        try:
            with target.open("rb") as fh:
                while chunk := fh.read(STREAM_CHUNK_BYTES):
                    yield chunk
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        _iter_file(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )


@router.get("/{run_id}/export/manifest")
@admin_router.get("/{run_id}/export/manifest")
def export_manifest(
    run_id: int,
    db: Session = Depends(get_db),
    _admin: AdminSession = Depends(require_admin_session),
) -> JSONResponse:
    """Conteggi dell'export senza trattenere i file generati."""
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_v2 {run_id} inesistente")

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"cecchino_run_v2_manifest_{run_id}_"))
    try:
        manifest = build_export_bundle(db, run_id=int(run_id), output_dir=tmp_dir)
        manifest["files"] = {name: name for name in manifest["files"]}
        return JSONResponse(content=jsonable_encoder(manifest))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
