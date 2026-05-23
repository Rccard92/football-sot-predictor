"""Endpoint job schedulabili (Railway Cron)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin_cron_secret
from app.core.config import get_settings, sportapi_configured
from app.core.database import get_db
from app.services.jobs.pre_match_lineup_refresh_job import PreMatchOfficialLineupRefreshJob

# Alias retrocompatibilità
PreMatchLineupRefreshJob = PreMatchOfficialLineupRefreshJob
from app.services.sportapi.sportapi_client import SportApiDisabledError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/jobs", tags=["admin-jobs"])


class PreMatchJobBody(BaseModel):
    force: bool = False
    minutes_before: int | None = Field(default=None, ge=5, le=120)
    window_minutes: int | None = Field(default=None, ge=2, le=60)
    season: int | None = None


def _run_pre_match_job(body: PreMatchJobBody | None, db: Session) -> dict[str, Any]:
    if not sportapi_configured():
        raise HTTPException(
            status_code=400,
            detail="SportAPI disabilitata: imposta SPORTAPI_ENABLED=true e SPORTAPI_RAPIDAPI_KEY",
        )
    settings = get_settings()
    season = int((body.season if body and body.season is not None else None) or settings.default_season)
    force = bool(body.force) if body else False
    minutes_before = body.minutes_before if body else None
    window_minutes = body.window_minutes if body else None
    try:
        return PreMatchOfficialLineupRefreshJob().run(
            db,
            season,
            force=force,
            minutes_before=minutes_before,
            window_minutes=window_minutes,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("pre-match job DB error")
        raise HTTPException(status_code=503, detail="Database error") from exc
    except SportApiDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/pre-match-official-lineups/run",
    response_model=None,
    dependencies=[Depends(require_admin_cron_secret)],
)
def run_pre_match_official_lineups(
    body: PreMatchJobBody | None = None,
    db: Session = Depends(get_db),
):
    return jsonable_encoder(_run_pre_match_job(body, db))


@router.post(
    "/pre-match-lineup-refresh/run",
    response_model=None,
    dependencies=[Depends(require_admin_cron_secret)],
)
def run_pre_match_lineup_refresh(
    body: PreMatchJobBody | None = None,
    db: Session = Depends(get_db),
):
    """Alias deprecato — usare pre-match-official-lineups/run."""
    return jsonable_encoder(_run_pre_match_job(body, db))
