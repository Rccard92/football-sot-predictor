"""Admin discovery arbitri e severità (API-Sports)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.referee_severity_service import RefereeSeverityService, build_referee_summary_for_fixture
from app.services.referee_sync_service import RefereeSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/referees", tags=["admin-referees"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


class RefereeSyncFixtureBody(BaseModel):
    fixture_id: int | None = None
    api_fixture_id: int | None = None

    @model_validator(mode="after")
    def _xor_ids(self) -> "RefereeSyncFixtureBody":
        has_fixture = self.fixture_id is not None
        has_api = self.api_fixture_id is not None
        if has_fixture == has_api:
            raise ValueError("Specificare esattamente uno tra fixture_id e api_fixture_id")
        return self


class RefereeProfileBody(BaseModel):
    referee_name: str | None = None
    league_id: int | None = None
    season: int | None = None
    fixture_id: int | None = None
    max_matches: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def _require_target(self) -> "RefereeProfileBody":
        if self.fixture_id is None and not (self.referee_name or "").strip():
            raise ValueError("Specificare referee_name oppure fixture_id")
        return self


@router.post("/sync-fixture", response_model=None)
def sync_referee_fixture(
    body: RefereeSyncFixtureBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_api_football_key()
    try:
        return jsonable_encoder(
            RefereeSyncService().sync_fixture(
                db,
                fixture_id=body.fixture_id,
                api_fixture_id=body.api_fixture_id,
            ),
        )
    except Exception as exc:
        logger.exception("referee sync-fixture failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/profile", response_model=None)
def compute_referee_profile(
    body: RefereeProfileBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_api_football_key()
    try:
        return jsonable_encoder(
            RefereeSeverityService().compute_profile(
                db,
                referee_name=body.referee_name,
                league_id=body.league_id,
                season=body.season,
                max_matches=body.max_matches,
                fixture_id=body.fixture_id,
            ),
        )
    except Exception as exc:
        logger.exception("referee profile failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/fixture/{fixture_id}/summary", response_model=None)
def get_referee_fixture_summary(
    fixture_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return jsonable_encoder(build_referee_summary_for_fixture(db, fixture_id))
