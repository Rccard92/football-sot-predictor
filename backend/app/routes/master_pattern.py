"""API Master Pattern: pattern vincenti 4/4 di V2, V2.5 e V3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.master_patterns import service

router = APIRouter(prefix="/admin/cecchino/master-pattern", tags=["admin-master-pattern"])


def _raise(exc: CecchinoLabImportError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(service.overview(db)))


@router.post("/builds")
def post_build(model: str = Query(...), db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(status_code=202, content=jsonable_encoder(service.start_build(db, model)))
    except CecchinoLabImportError as exc:
        _raise(exc)


@router.get("/patterns")
def get_patterns(
    model: str = Query(...),
    target_type: str = Query(default="market"),
    market: str | None = Query(default=None),
    min_matches: int | None = Query(default=None, ge=0),
    min_quota: float | None = Query(default=None, ge=0),
    max_quota: float | None = Query(default=None, ge=0),
    sort: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    out = service.list_patterns(
        db,
        model=model,
        target_type=target_type,
        market=market,
        min_matches=min_matches,
        min_quota=min_quota,
        max_quota=max_quota,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(content=jsonable_encoder(out))


@router.get("/patterns/{pattern_id}")
def get_pattern_detail(pattern_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(service.pattern_detail(db, pattern_id)))
    except CecchinoLabImportError as exc:
        _raise(exc)
