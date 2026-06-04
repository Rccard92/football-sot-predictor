"""Route API Cecchino Today — discovery giornaliera."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_today import CecchinoTodayScanBody
from app.services.cecchino.cecchino_today_service import (
    get_today_fixture_detail,
    list_eligible_today,
    list_excluded_today,
    run_scan,
)

router = APIRouter(prefix="/cecchino/today", tags=["cecchino-today"])
admin_router = APIRouter(prefix="/admin/cecchino/today", tags=["admin-cecchino-today"])


@router.get("")
def cecchino_today_list(
    date: date | None = Query(default=None, alias="date"),
    country: str | None = Query(default=None),
    league: str | None = Query(default=None),
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = list_eligible_today(
        db,
        scan_date=date,
        country=country,
        league=league,
        timezone=timezone,
    )
    return jsonable_encoder(payload)


@router.get("/{today_fixture_id}")
def cecchino_today_detail(
    today_fixture_id: int,
    db: Session = Depends(get_db),
):
    payload = get_today_fixture_detail(db, today_fixture_id)
    if payload is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Not found"})
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/scan")
def cecchino_today_scan(
    body: CecchinoTodayScanBody | None = None,
    db: Session = Depends(get_db),
):
    req = body or CecchinoTodayScanBody()
    payload = run_scan(db, scan_date=req.scan_date, timezone=req.timezone)
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.get("/excluded")
def cecchino_today_excluded(
    date: date | None = Query(default=None, alias="date"),
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = list_excluded_today(db, scan_date=date, timezone=timezone)
    return jsonable_encoder(payload)
