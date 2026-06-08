"""Route API Cecchino Today — discovery giornaliera."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cecchino_today import (
    CecchinoTodayCleanupBody,
    CecchinoTodayRefreshBetfairBody,
    CecchinoTodayRevalidateDayBody,
    CecchinoTodayScanBody,
    CecchinoTodayScanDayBody,
    CecchinoTodayUpdateResultsBody,
)
from app.services.cecchino.cecchino_today_betfair_refresh import (
    get_betfair_markets_json_by_id,
    refresh_betfair_odds_by_id,
)
from app.services.cecchino.cecchino_today_scan_job_service import (
    get_latest_scan_job,
    get_scan_job,
    job_to_dict,
    recover_stale_scan_jobs,
    start_scan_job,
)
from app.services.cecchino.cecchino_kpi_debug_json import get_kpi_debug_json
from app.services.cecchino.cecchino_today_service import (
    cleanup_cecchino_today_snapshots,
    debug_search,
    get_today_fixture_detail,
    list_available_days,
    list_eligible_today,
    list_excluded_today,
    revalidate_cecchino_today_day,
    run_scan,
    run_scan_day,
    run_scan_today,
    run_scan_tomorrow,
    update_today_fixture_results,
)

router = APIRouter(prefix="/cecchino/today", tags=["cecchino-today"])
admin_router = APIRouter(prefix="/admin/cecchino/today", tags=["admin-cecchino-today"])


@router.get("/days")
def cecchino_today_days(
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = list_available_days(db, timezone=timezone)
    return jsonable_encoder(payload)


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


@router.post("/{today_fixture_id}/refresh-betfair-odds")
def cecchino_today_refresh_betfair_odds(
    today_fixture_id: int,
    body: CecchinoTodayRefreshBetfairBody | None = None,
    db: Session = Depends(get_db),
):
    req = body or CecchinoTodayRefreshBetfairBody()
    payload = refresh_betfair_odds_by_id(
        db,
        today_fixture_id,
        force=req.force,
        rebuild_kpi=req.rebuild_kpi,
    )
    if payload is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Not found"})
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@router.get("/{today_fixture_id}/betfair-markets-json")
def cecchino_today_betfair_markets_json(
    today_fixture_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    payload = get_betfair_markets_json_by_id(db, today_fixture_id, force=force)
    if payload is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Not found"})
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@router.get("/{today_fixture_id}/kpi-debug-json")
def cecchino_today_kpi_debug_json(
    today_fixture_id: int,
    db: Session = Depends(get_db),
):
    payload = get_kpi_debug_json(db, today_fixture_id)
    if payload is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Not found"})
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


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


@admin_router.post("/scan-today")
def cecchino_today_scan_today(
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = run_scan_today(db, timezone=timezone)
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/scan-tomorrow")
def cecchino_today_scan_tomorrow(
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = run_scan_tomorrow(db, timezone=timezone)
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/scan-day/start")
def cecchino_today_scan_day_start(
    body: CecchinoTodayScanDayBody,
    db: Session = Depends(get_db),
):
    payload = start_scan_job(
        db,
        scan_date=body.date,
        timezone=body.timezone,
        force_rescan=body.force_rescan,
    )
    if payload.get("status") == "conflict":
        return JSONResponse(status_code=409, content=jsonable_encoder(payload))
    status_code = 200 if payload.get("status") in ("queued", "running", "already_scanned") else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.get("/scan-jobs/latest")
def cecchino_today_scan_job_latest(
    date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    recover_stale_scan_jobs(db)
    job = get_latest_scan_job(db, date)
    if job is None:
        return JSONResponse(status_code=200, content=None)
    return jsonable_encoder(job_to_dict(job))


@admin_router.get("/scan-jobs/{job_id}")
def cecchino_today_scan_job_status(
    job_id: str,
    db: Session = Depends(get_db),
):
    recover_stale_scan_jobs(db)
    job = get_scan_job(db, job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found"})
    return jsonable_encoder(job_to_dict(job))


@admin_router.post("/scan-day")
def cecchino_today_scan_day(
    body: CecchinoTodayScanDayBody,
    sync: bool = Query(default=False, description="Modalità sync debug (deprecata)"),
    db: Session = Depends(get_db),
):
    if sync:
        payload = run_scan_day(
            db,
            scan_date=body.date,
            timezone=body.timezone,
            force_rescan=body.force_rescan,
        )
        status_code = 200 if payload.get("status") in ("ok", "already_scanned") else 422
        return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))

    payload = start_scan_job(
        db,
        scan_date=body.date,
        timezone=body.timezone,
        force_rescan=body.force_rescan,
    )
    if payload.get("status") == "conflict":
        return JSONResponse(status_code=409, content=jsonable_encoder(payload))
    status_code = 200 if payload.get("status") in ("queued", "running", "already_scanned") else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/update-results")
def cecchino_today_update_results(
    body: CecchinoTodayUpdateResultsBody | None = None,
    db: Session = Depends(get_db),
):
    req = body or CecchinoTodayUpdateResultsBody()
    payload = update_today_fixture_results(
        db,
        scan_date=req.target_date,
        timezone=req.timezone,
    )
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@admin_router.post("/cleanup")
def cecchino_today_cleanup(
    body: CecchinoTodayCleanupBody | None = None,
    db: Session = Depends(get_db),
):
    req = body or CecchinoTodayCleanupBody()
    payload = cleanup_cecchino_today_snapshots(
        db,
        retention_days=req.retention_days,
        timezone=req.timezone,
        commit=True,
    )
    return jsonable_encoder(payload)


@admin_router.get("/debug-search")
def cecchino_today_debug_search(
    q: str = Query(..., min_length=1),
    date: date | None = Query(default=None, alias="date"),
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = debug_search(db, scan_date=date, q=q, timezone=timezone)
    return jsonable_encoder(payload)


@admin_router.get("/excluded")
def cecchino_today_excluded(
    date: date | None = Query(default=None, alias="date"),
    timezone: str = Query(default="Europe/Rome"),
    db: Session = Depends(get_db),
):
    payload = list_excluded_today(db, scan_date=date, timezone=timezone)
    return jsonable_encoder(payload)


@admin_router.post("/revalidate-day")
def cecchino_today_revalidate_day(
    body: CecchinoTodayRevalidateDayBody,
    db: Session = Depends(get_db),
):
    payload = revalidate_cecchino_today_day(db, scan_date=body.date)
    status_code = 200 if payload.get("status") == "ok" else 422
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))
