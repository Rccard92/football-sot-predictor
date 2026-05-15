"""Diagnostica read-only sulla copertura expected_goals (xG) in fixture_team_stats."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Fixture, FixtureTeamStat, Team
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug", tags=["admin-debug-expected-goals"])


@router.get("/serie-a/{season}/expected-goals-summary", response_model=None)
def expected_goals_summary_serie_a(
    season: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    season_f = Fixture.season_id == season_row.id
    try:
        rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureTeamStat)
                .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
                .where(season_f),
            )
            or 0,
        )
        rows_with_expected_goals = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureTeamStat)
                .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
                .where(season_f, FixtureTeamStat.expected_goals.isnot(None)),
            )
            or 0,
        )
        sample_rows = db.execute(
            select(
                Fixture.id.label("fixture_id"),
                Team.name.label("team_name"),
                FixtureTeamStat.expected_goals,
                FixtureTeamStat.side,
            )
            .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
            .join(Team, Team.id == FixtureTeamStat.team_id)
            .where(season_f, FixtureTeamStat.expected_goals.isnot(None))
            .order_by(Fixture.kickoff_at.desc(), Fixture.id.desc())
            .limit(10),
        ).all()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("expected-goals-summary DB error: %s", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc

    coverage_pct = round(100.0 * rows_with_expected_goals / rows_total, 2) if rows_total else 0.0
    sample = [
        {
            "fixture_id": int(r.fixture_id),
            "team_name": str(r.team_name),
            "side": r.side,
            "expected_goals": float(r.expected_goals) if r.expected_goals is not None else None,
        }
        for r in sample_rows
    ]

    return {
        "status": "success",
        "season": int(season),
        "rows_total": rows_total,
        "rows_with_expected_goals": rows_with_expected_goals,
        "coverage_pct": coverage_pct,
        "sample": sample,
    }
