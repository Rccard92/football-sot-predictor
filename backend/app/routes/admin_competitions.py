from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.competition import (
    CompetitionCreateBody,
    CompetitionDiscoverBody,
    CompetitionDiscoverResponse,
    CompetitionPatchBody,
    CompetitionRead,
)
from app.services.competition_backfill_service import CompetitionBackfillService
from app.services.competition_service import CompetitionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/competitions", tags=["admin-competitions"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(status_code=400, detail="API_FOOTBALL_KEY non configurata sul server")


@router.post("/discover")
def discover_competitions(body: CompetitionDiscoverBody, db: Session = Depends(get_db)):
    _require_api_football_key()
    svc = CompetitionService()
    result = svc.discover(db, country=body.country, name_query=body.name_query, season=body.season)
    return jsonable_encoder(CompetitionDiscoverResponse.model_validate(result).model_dump())


@router.post("")
def create_competition(body: CompetitionCreateBody, db: Session = Depends(get_db)):
    svc = CompetitionService()
    row = svc.create(db, body.model_dump())
    return jsonable_encoder(CompetitionRead.model_validate(row).model_dump())


@router.patch("/{competition_id}")
def patch_competition(
    competition_id: int,
    body: CompetitionPatchBody,
    db: Session = Depends(get_db),
):
    svc = CompetitionService()
    patch_data = body.model_dump(exclude_unset=True)
    row = svc.patch(db, competition_id, patch_data)
    return jsonable_encoder(CompetitionRead.model_validate(row).model_dump())


@router.post("/backfill/serie-a/{season}")
def backfill_serie_a_competition(season: int, db: Session = Depends(get_db)):
    svc = CompetitionBackfillService()
    result = svc.backfill_serie_a(db, season_year=season)
    return jsonable_encoder(result)
