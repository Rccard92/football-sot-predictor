"""API RUN V2 Cecchino Lab.

Control plane (start/resume/cancel) e export/manifest/AI-bundle: sessione admin.
Il pacchetto AI si prepara via job async (POST jobs → poll → download).
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
    build_export_manifest_light,
)
from app.services.cecchino_data_lab.run_v2 import ai_bundle_jobs
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
    """Manifest leggero: solo COUNT/metadata, nessuna generazione FULL/LONG/RAW."""
    try:
        manifest = build_export_manifest_light(db, run_id=int(run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=jsonable_encoder(manifest))


@router.post("/{run_id}/export/ai-bundle/jobs")
@admin_router.post("/{run_id}/export/ai-bundle/jobs")
def create_ai_bundle_job(
    run_id: int,
    db: Session = Depends(get_db),
    _admin: AdminSession = Depends(require_admin_session),
) -> JSONResponse:
    """Crea o riusa job export AI (idempotente per run_id + export_schema_version)."""
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_v2 {run_id} inesistente")
    try:
        job = ai_bundle_jobs.create_or_reuse_job(int(run_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=jsonable_encoder(job.to_status_dict()))


@router.get("/{run_id}/export/ai-bundle/jobs/{job_id}")
@admin_router.get("/{run_id}/export/ai-bundle/jobs/{job_id}")
def get_ai_bundle_job(
    run_id: int,
    job_id: str,
    _admin: AdminSession = Depends(require_admin_session),
) -> JSONResponse:
    job = ai_bundle_jobs.get_job(job_id)
    if job is None or int(job.run_id) != int(run_id):
        raise HTTPException(status_code=404, detail="ai_bundle_job_not_found")
    return JSONResponse(content=jsonable_encoder(job.to_status_dict()))


@router.get("/{run_id}/export/ai-bundle/download")
@admin_router.get("/{run_id}/export/ai-bundle/download")
def download_ai_bundle(
    run_id: int,
    _admin: AdminSession = Depends(require_admin_session),
) -> StreamingResponse:
    """Serve lo ZIP già costruito (nessuna rigenerazione)."""
    try:
        path, filename, size = ai_bundle_jobs.resolve_download(int(run_id))
    except ValueError as exc:
        code = str(exc)
        status = 404 if code in ("ai_bundle_not_ready", "ai_bundle_missing_file") else 400
        raise HTTPException(status_code=status, detail=code) from exc

    def _iter_file() -> Iterator[bytes]:
        with path.open("rb") as fh:
            while chunk := fh.read(STREAM_CHUNK_BYTES):
                yield chunk

    return StreamingResponse(
        _iter_file(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-AI-Bundle-Bytes": str(size),
            "X-AI-Bundle-Cached": "1",
        },
    )


@router.get("/{run_id}/export/ai-bundle")
@admin_router.get("/{run_id}/export/ai-bundle")
def export_ai_bundle_legacy(
    run_id: int,
    _admin: AdminSession = Depends(require_admin_session),
) -> JSONResponse:
    """Legacy sync disabilitato: usare POST .../jobs + poll + download."""
    raise HTTPException(
        status_code=409,
        detail={
            "error": "ai_bundle_sync_disabled",
            "message": (
                "La generazione sincrona del pacchetto AI e' disabilitata. "
                "Usa POST /export/ai-bundle/jobs, poi poll status e GET .../download."
            ),
            "run_id": int(run_id),
        },
    )
