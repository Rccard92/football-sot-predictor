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


@router.get("/v3/v32-exam")
def get_v32_exam(start: bool = Query(default=False)) -> JSONResponse:
    """Esame V3.2 (docs/v3/V32_ESAME_PREREGISTRAZIONE.md): `start=true` lo avvia in sottofondo, poi si legge lo stato."""
    from app.services.cecchino_v3_live.v32_exam import exam_state

    return JSONResponse(content=jsonable_encoder(exam_state(start=start)))


@router.get("/v5/league-map")
def get_league_map(start: bool = Query(default=False)) -> JSONResponse:
    """Mappa dei 16 campionati (docs/campionati/MAPPA_V1_PREREGISTRAZIONE.md): `start=true` la calcola in sottofondo."""
    from app.services.cecchino_v5.league_map import map_state

    return JSONResponse(content=jsonable_encoder(map_state(start=start)))


@router.get("/v5/combo-exam")
def get_combo_exam(start: bool = Query(default=False)) -> JSONResponse:
    """Esame combo v1 (docs/combo/COMBO_V1_PREREGISTRAZIONE.md): `start=true` lo avvia in sottofondo."""
    from app.services.cecchino_v5.combo_exam import exam_state

    return JSONResponse(content=jsonable_encoder(exam_state(start=start)))


@router.get("/v5/pattern-search")
def get_pattern_search(start: bool = Query(default=False)) -> JSONResponse:
    """Ricerca ampia dei pattern (docs/campionati/PATTERN_V1_PREREGISTRAZIONE.md): `start=true` la avvia in sottofondo."""
    from app.services.cecchino_v5.pattern_search import search_state

    return JSONResponse(content=jsonable_encoder(search_state(start=start)))
