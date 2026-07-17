"""Availability dati locali per audit Intensità Goal v5 — Fase 1A.3."""

from __future__ import annotations

from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

_FT_RESULT_CLAUSES = (
    Fixture.status.in_(tuple(FINISHED_STATUSES)),
    Fixture.goals_home.is_not(None),
    Fixture.goals_away.is_not(None),
    Fixture.home_team_id.is_not(None),
    Fixture.away_team_id.is_not(None),
    Fixture.kickoff_at.is_not(None),
)


def build_goal_intensity_v5_availability(db: Session) -> dict[str, Any]:
    """Aggregato read-only su Fixture FT con risultato (kickoff range disponibile)."""
    count = int(db.scalar(select(func.count(Fixture.id)).where(*_FT_RESULT_CLAUSES)) or 0)
    earliest = db.scalar(select(func.min(Fixture.kickoff_at)).where(*_FT_RESULT_CLAUSES))
    latest = db.scalar(select(func.max(Fixture.kickoff_at)).where(*_FT_RESULT_CLAUSES))

    comp_ids = list(
        db.scalars(
            select(distinct(Fixture.competition_id)).where(
                *_FT_RESULT_CLAUSES,
                Fixture.competition_id.is_not(None),
            )
        ).all()
    )
    competitions = sorted(int(c) for c in comp_ids if c is not None)

    countries: list[str] = []
    if competitions:
        countries = sorted(
            {
                str(c.country)
                for c in db.scalars(select(Competition).where(Competition.id.in_(competitions))).all()
                if c.country
            }
        )

    earliest_u = ensure_datetime_utc(earliest, field_name="earliest") if earliest is not None else None
    latest_u = ensure_datetime_utc(latest, field_name="latest") if latest is not None else None

    return {
        "status": "ok",
        "finished_fixtures_with_result": count,
        "earliest_kickoff": safe_isoformat(earliest_u, field_name="earliest") if earliest_u else None,
        "latest_kickoff": safe_isoformat(latest_u, field_name="latest") if latest_u else None,
        "earliest_kickoff_date": earliest_u.date().isoformat() if earliest_u else None,
        "latest_kickoff_date": latest_u.date().isoformat() if latest_u else None,
        "competitions_count": len(competitions),
        "competition_ids": competitions[:200],
        "countries_count": len(countries),
        "countries": countries[:100],
        "cohort_basis": "fixture_kickoff_at",
    }
