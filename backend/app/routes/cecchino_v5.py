"""API Cecchino V5 (docs/v5/LIVE_REGOLE.md): sola lettura pubblica su /api/cecchino/v5 e confronto dei motori."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.services.audit.readonly import readonly_session
from app.services.cecchino_v5 import serving

router = APIRouter(prefix="/cecchino", tags=["cecchino-v5"])


def _parse_date(raw: str | None) -> date:
    if raw is None or not raw.strip():
        return serving.today_rome()
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"data non valida: {raw}") from exc


@router.get("/v5/plays")
def get_v5_plays(date_: str | None = Query(default=None, alias="date"), db: Session = Depends(readonly_session)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(serving.v5_day(db, _parse_date(date_))))


@router.get("/engines/compare")
def get_engines_compare(days: int = Query(default=30, ge=1, le=120), db: Session = Depends(readonly_session)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(serving.engines_compare(db, days=days)))


@router.get("/v5/today-fixture/{today_fixture_id}")
def get_v5_today_fixture(today_fixture_id: int, db: Session = Depends(readonly_session)) -> JSONResponse:
    from app.services.cecchino_v5.fixture_view import fixture_view

    return JSONResponse(content=jsonable_encoder(fixture_view(db, today_fixture_id)))
