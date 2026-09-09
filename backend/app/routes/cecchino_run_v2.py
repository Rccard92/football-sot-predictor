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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.services.cecchino_data_lab.run_v2.export import (
    EXPORT_FILES,
    FILE_FULL,
    build_export_bundle,
)

router = APIRouter(prefix="/cecchino-run-v2", tags=["cecchino-run-v2"])
admin_router = APIRouter(prefix="/admin/cecchino-run-v2", tags=["admin-cecchino-run-v2"])
logger = logging.getLogger(__name__)

STREAM_CHUNK_BYTES = 1024 * 512


def _run_to_dict(run: CecchinoRunV2Run) -> dict[str, Any]:
    return {
        "run_id": int(run.id),
        "run_version": run.run_version,
        "status": run.status,
        "run_scope": run.run_scope,
        "max_matches": run.max_matches,
        "requested_at": run.requested_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "matches_total": run.matches_total,
        "matches_processed": run.matches_processed,
        "matches_error": run.matches_error,
        "market_rows_written": run.market_rows_written,
        "leakage_violations": run.leakage_violations,
        "progress_pct": run.progress_pct,
        "min_kickoff_at": run.min_kickoff_at,
        "max_kickoff_at": run.max_kickoff_at,
        "quote_policy": run.quote_policy_json,
        "module_policy": run.module_policy_json,
        "summary": run.summary_json,
        "leakage_audit": run.leakage_audit_json,
        "error": run.error_json,
    }


@router.get("")
@admin_router.get("")
def list_runs(db: Session = Depends(get_db)) -> JSONResponse:
    runs = list(
        db.scalars(select(CecchinoRunV2Run).order_by(CecchinoRunV2Run.id.desc())).all()
    )
    return JSONResponse(content=jsonable_encoder({"items": [_run_to_dict(r) for r in runs]}))


@router.get("/{run_id}")
@admin_router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_v2 {run_id} inesistente")
    return JSONResponse(content=jsonable_encoder(_run_to_dict(run)))


@router.get("/{run_id}/export")
@admin_router.get("/{run_id}/export")
def export_run(
    run_id: int,
    file: str = Query(FILE_FULL, description=f"Uno fra: {', '.join(EXPORT_FILES)}"),
    db: Session = Depends(get_db),
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
def export_manifest(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
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
