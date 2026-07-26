"""Route Cecchino Lab — archivio storico Football-Data (thin routers)."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino_data_lab.competition_catalog import list_competitions_dicts
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.import_service import import_csv_bytes
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes
from app.services.cecchino_data_lab.query_service import (
    get_dataset,
    get_match,
    get_overview,
    list_data_quality_issues,
    list_datasets,
    list_matches,
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


@router.get("/catalog/competitions")
def catalog_competitions() -> dict[str, Any]:
    return {"items": list_competitions_dicts()}


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_overview(db)


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
        page=page,
        page_size=page_size,
    )
