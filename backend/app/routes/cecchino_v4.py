"""API Cecchino V4 (docs/v4/API.md). Lettura pubblica su /api/cecchino/v4, azioni su /api/admin/cecchino/v4
con sessione admin obbligatoria. Il modulo e' isolato: nessuna dipendenza da altri modelli."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.admin_session import require_admin_session
from app.core.database import get_db
from app.services.cecchino_v4 import serving
from app.services.cecchino_v4.pipeline import dispatch
from app.services.cecchino_v4.settings import v4_enabled

router = APIRouter(prefix="/cecchino/v4", tags=["cecchino-v4"])
admin_router = APIRouter(
    prefix="/admin/cecchino/v4",
    tags=["admin-cecchino-v4"],
    dependencies=[Depends(require_admin_session)],
)


def _json(payload) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(payload))


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "error", "message": message})


def _parse_date(raw: str | None, default: date | None = None) -> date:
    if raw is None or not raw.strip():
        if default is None:
            raise HTTPException(status_code=422, detail="parametro date mancante")
        return default
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"data non valida: {raw}") from exc


@router.get("/status")
def get_status() -> JSONResponse:
    return _json({"enabled": v4_enabled(), "module": "cecchino_v4"})


@router.get("/days")
def get_days(
    from_: str | None = Query(default=None, alias="from"),
    days: int = Query(default=7, ge=1, le=14),
    db: Session = Depends(get_db),
) -> JSONResponse:
    start = _parse_date(from_, default=serving.default_days()[0])
    return _json(serving.days(db, start, days))


@router.get("/fixtures")
def get_fixtures(
    date_: str | None = Query(default=None, alias="date"),
    league: str | None = Query(default=None),
    only_plays: bool = Query(default=False),
    only_lineups: bool = Query(default=False),
    sort: str = Query(default="kickoff", pattern="^(kickoff|profit)$"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    day = _parse_date(date_, default=serving.default_days()[0])
    return _json(serving.fixtures(db, day, league=league, only_plays=only_plays, only_lineups=only_lineups, sort=sort))


@router.get("/fixtures/{fixture_id}")
def get_fixture(fixture_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return _json(serving.fixture_detail(db, fixture_id))
    except serving.NotFound as exc:
        return _error(404, str(exc))


@router.get("/shortlist")
def get_shortlist(date_: str | None = Query(default=None, alias="date"), db: Session = Depends(get_db)) -> JSONResponse:
    day = _parse_date(date_, default=serving.default_days()[0])
    return _json(serving.shortlist(db, day))


@router.get("/measure/summary")
def get_measure_summary(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    start = _parse_date(from_, default=date(2000, 1, 1)) if from_ else None
    end = _parse_date(to, default=date(2100, 1, 1)) if to else None
    return _json(serving.measure_summary(db, start, end))


@router.get("/engine/exams")
def get_exams(db: Session = Depends(get_db)) -> JSONResponse:
    return _json(serving.exams(db))


@router.get("/engine/challengers")
def get_challengers(db: Session = Depends(get_db)) -> JSONResponse:
    return _json(serving.challengers(db))


@router.get("/engine/data")
def get_engine_data(db: Session = Depends(get_db)) -> JSONResponse:
    return _json(serving.engine_data(db))


# --- Azioni (sessione admin) ------------------------------------------------------------


@admin_router.get("/jobs")
def get_jobs(db: Session = Depends(get_db)) -> JSONResponse:
    return _json(serving.jobs(db))


@admin_router.post("/jobs/{name}/run")
def post_job_run(name: str, date_: str | None = Query(default=None, alias="date"), db: Session = Depends(get_db)) -> JSONResponse:
    if not v4_enabled():
        return _error(409, "Cecchino V4 disattivata: impostare CECCHINO_V4_ENABLED=true")
    params = {"date": date_} if date_ else {}
    try:
        job_id = dispatch.start(name, params)
    except dispatch.UnknownJobName as exc:
        return _error(404, str(exc))
    except dispatch.JobBusy as exc:
        return _error(409, str(exc))
    return JSONResponse(status_code=202, content={"job_id": job_id, "name": name})


@admin_router.post("/shortlist/{date_}/seal")
def post_shortlist_seal(date_: str, db: Session = Depends(get_db)) -> JSONResponse:
    day = _parse_date(date_)
    try:
        return _json(dispatch.seal(db, day))
    except ValueError as exc:
        return _error(409, str(exc))


@admin_router.post("/exams/{code}/run")
def post_exam_run(code: str) -> JSONResponse:
    try:
        job_id = dispatch.start(f"exam_{code.upper()}", {})
    except dispatch.UnknownJobName as exc:
        return _error(404, str(exc))
    except dispatch.JobBusy as exc:
        return _error(409, str(exc))
    return JSONResponse(status_code=202, content={"job_id": job_id, "exam": code.upper()})
