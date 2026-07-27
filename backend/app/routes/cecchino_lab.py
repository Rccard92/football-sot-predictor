"""Route Cecchino Lab — archivio storico Football-Data (thin routers)."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino_data_lab.analytics_service import get_analytics_overview
from app.services.cecchino_data_lab.competition_catalog import list_competitions_dicts
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.import_service import import_csv_bytes
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes
from app.services.cecchino_data_lab.batch_preview_service import batch_preview_csv_files
from app.services.cecchino_data_lab.replace_service import replace_dataset_csv
from app.services.cecchino_data_lab.query_service import (
    export_data_quality_issues,
    get_dataset,
    get_match,
    get_overview,
    list_data_quality_issues,
    list_datasets,
    list_matches,
)
from app.services.cecchino_data_lab.historical_scan_preflight import run_historical_scan_preflight
from app.services.cecchino_data_lab.historical_scan_service import (
    cancel_historical_scan,
    get_historical_scan,
    list_historical_scans,
    list_run_matches,
    resume_historical_scan,
    start_historical_scan,
)
from app.services.cecchino_data_lab.historical_ai_report import (
    build_ai_report_zip_bytes,
    iter_report_chunks,
)

router = APIRouter(prefix="/cecchino-lab", tags=["cecchino-lab"])
admin_router = APIRouter(prefix="/admin/cecchino-lab", tags=["admin-cecchino-lab"])


@admin_router.post("/imports/preview")
async def preview_import(
    file: UploadFile = File(...),
    competition_key: str = Form(...),
    season_label: str = Form(...),
) -> JSONResponse:
    raw = await file.read()
    try:
        result = preview_csv_bytes(
            raw,
            competition_key=competition_key,
            season_label=season_label,
            source_filename=file.filename,
        )
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "error": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            ),
        )
    return JSONResponse(content=jsonable_encoder(result))


@admin_router.post("/imports/batch/preview")
async def batch_preview_import(
    files: list[UploadFile] = File(...),
    season_label: str = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    file_tuples: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        file_tuples.append((f.filename or "upload.csv", raw))
    try:
        result = batch_preview_csv_files(
            db,
            file_tuples,
            season_label=season_label,
        )
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "error": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            ),
        )
    return JSONResponse(content=jsonable_encoder(result))


@admin_router.post("/imports")
async def run_import(
    file: UploadFile = File(...),
    competition_key: str = Form(...),
    season_label: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    raw = await file.read()
    try:
        result = import_csv_bytes(
            db,
            raw,
            competition_key=competition_key,
            season_label=season_label,
            source_filename=file.filename or "upload.csv",
            confirm=confirm,
        )
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "error": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            ),
        )
    return JSONResponse(content=jsonable_encoder(result))


@admin_router.post("/datasets/{dataset_id}/replace")
async def replace_dataset(
    dataset_id: int,
    file: UploadFile = File(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    raw = await file.read()
    try:
        result = replace_dataset_csv(
            db,
            dataset_id,
            raw,
            source_filename=file.filename or "upload.csv",
            confirm=confirm,
        )
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "error": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            ),
        )
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/catalog/competitions")
def catalog_competitions() -> dict[str, Any]:
    return {"items": list_competitions_dicts()}


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_overview(db)


@router.get("/analytics/overview")
def analytics_overview(
    season_label: str | None = None,
    country: str | None = None,
    competition: str | None = None,
    dataset_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dashboard storica betting (read-only). Nessuna predizione / formula Cecchino."""
    return get_analytics_overview(
        db,
        season_label=season_label,
        country=country,
        competition=competition,
        dataset_id=dataset_id,
    )


@router.get("/datasets")
def datasets(
    country: str | None = None,
    competition: str | None = None,
    season: str | None = None,
    quality_status: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_datasets(
        db,
        country=country,
        competition=competition,
        season=season,
        quality_status=quality_status,
    )


@router.get("/datasets/{dataset_id}")
def dataset_detail(dataset_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = get_dataset(db, dataset_id)
    if result is None:
        raise HTTPException(status_code=404, detail="dataset_not_found")
    return result


@router.get("/matches")
def matches(
    dataset_id: int | None = None,
    competition: str | None = None,
    season: str | None = None,
    team: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    result: str | None = None,
    quality_status: str | None = None,
    has_bet365_1x2: bool | None = None,
    has_bet365_ou25: bool | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = "match_date",
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_matches(
        db,
        dataset_id=dataset_id,
        competition=competition,
        season=season,
        team=team,
        date_from=date_from,
        date_to=date_to,
        result=result,
        quality_status=quality_status,
        has_bet365_1x2=has_bet365_1x2,
        has_bet365_ou25=has_bet365_ou25,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/matches/{match_id}")
def match_detail(match_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = get_match(db, match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="match_not_found")
    return result


@router.get("/data-quality/issues")
def data_quality_issues(
    dataset_id: int | None = None,
    import_id: int | None = None,
    severity: str | None = None,
    issue_code: str | None = None,
    match_id: int | None = None,
    competition: str | None = None,
    season_label: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_data_quality_issues(
        db,
        dataset_id=dataset_id,
        import_id=import_id,
        severity=severity,
        issue_code=issue_code,
        match_id=match_id,
        competition=competition,
        season_label=season_label,
        page=page,
        page_size=page_size,
    )


@router.get("/data-quality/issues/export")
def data_quality_issues_export(
    format: str = Query("json", pattern="^(csv|json)$"),
    scope: str = Query("filtered", pattern="^(filtered|all)$"),
    severity: str | None = None,
    issue_code: str | None = None,
    dataset_id: int | None = None,
    competition: str | None = None,
    season_label: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export completo segnalazioni qualità (CSV UTF-8 BOM `;` oppure JSON). Nessuna paginazione."""
    content, media_type, filename = export_data_quality_issues(
        db,
        format=format,
        scope=scope,
        severity=severity,
        issue_code=issue_code,
        dataset_id=dataset_id,
        competition=competition,
        season_label=season_label,
    )
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type=media_type,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Historical scans (Cecchino Lab only — offline replay Bet365)
# ---------------------------------------------------------------------------


@admin_router.post("/historical-scans/preflight")
def historical_scan_preflight(
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> JSONResponse:
    season_label = str((body or {}).get("season_label") or "").strip()
    if not season_label:
        raise HTTPException(status_code=400, detail="season_label richiesto")
    result = run_historical_scan_preflight(db, season_label=season_label)
    return JSONResponse(content=jsonable_encoder(result))


@admin_router.post("/historical-scans")
def historical_scan_start(
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> JSONResponse:
    season_label = str((body or {}).get("season_label") or "").strip()
    confirm = (body or {}).get("confirm")
    max_matches = (body or {}).get("max_matches")
    try:
        result = start_historical_scan(
            db,
            season_label=season_label,
            confirm=confirm,
            max_matches=max_matches,
            background=True,
        )
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    return JSONResponse(content=jsonable_encoder(result), status_code=202)


@admin_router.post("/historical-scans/{run_id}/resume")
def historical_scan_resume(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        result = resume_historical_scan(db, run_id, background=True)
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    return JSONResponse(content=jsonable_encoder(result), status_code=202)


@admin_router.post("/historical-scans/{run_id}/cancel")
def historical_scan_cancel(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        result = cancel_historical_scan(db, run_id)
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/historical-scans")
def historical_scans_list(
    season_label: str | None = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(list_historical_scans(db, season_label=season_label))
    )


@router.get("/historical-scans/{run_id}")
def historical_scan_detail(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        result = get_historical_scan(db, run_id)
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/historical-scans/{run_id}/matches")
def historical_scan_matches(
    run_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    eligibility: str | None = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        result = list_run_matches(
            db, run_id, limit=limit, offset=offset, eligibility=eligibility
        )
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/historical-scans/{run_id}/summary")
def historical_scan_summary(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        result = get_historical_scan(db, run_id)
    except CecchinoLabImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "run_id": run_id,
                "status": result.get("status"),
                "summary": result.get("summary"),
                "preflight": result.get("preflight"),
                "progress_pct": result.get("progress_pct"),
                "matches_processed": result.get("matches_processed"),
                "matches_total": result.get("matches_total"),
                "matches_eligible_core": result.get("matches_eligible_core"),
                "matches_excluded": result.get("matches_excluded"),
                "matches_error": result.get("matches_error"),
            }
        )
    )


@router.get("/historical-scans/{run_id}/report")
def historical_scan_report(
    run_id: int,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        filename, data = build_ai_report_zip_bytes(db, run_id)
    except CecchinoLabImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter_report_chunks(data),
        media_type="application/zip",
        headers=headers,
    )
