"""API Monitoraggio Segno 1 — coorte storica vittorie casalinghe (esito reale 1)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino.cecchino_home_wins_monitoring import (
    build_home_wins_export_zip,
    get_home_win_detail,
    list_home_wins,
)

router = APIRouter(prefix="/cecchino/home-wins", tags=["cecchino-home-wins"])


def _filters(
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
    country: str | None,
    league: str | None,
    team: str | None,
    completeness: str | None,
) -> dict:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "competition_id": competition_id,
        "country": country,
        "league": league,
        "team": team,
        "completeness": completeness,
    }


@router.get("")
def home_wins_list(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    country: str | None = Query(default=None),
    league: str | None = Query(default=None),
    team: str | None = Query(default=None),
    completeness: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    payload = list_home_wins(
        db,
        **_filters(
            date_from, date_to, competition_id, country, league, team, completeness
        ),
        page=page,
        page_size=page_size,
    )
    return jsonable_encoder(payload)


@router.get("/export")
def home_wins_export(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    competition_id: int | None = Query(default=None),
    country: str | None = Query(default=None),
    league: str | None = Query(default=None),
    team: str | None = Query(default=None),
    completeness: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    content, filename = build_home_wins_export_zip(
        db,
        **_filters(
            date_from, date_to, competition_id, country, league, team, completeness
        ),
    )
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{today_fixture_id}")
def home_wins_detail(
    today_fixture_id: int,
    db: Session = Depends(get_db),
):
    payload = get_home_win_detail(db, today_fixture_id)
    if payload.get("status") == "error":
        code = 404 if payload.get("reason") in {"not_found", "not_in_home_wins_cohort"} else 400
        return JSONResponse(status_code=code, content=jsonable_encoder(payload))
    return jsonable_encoder(payload)
