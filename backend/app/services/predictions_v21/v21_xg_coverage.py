"""Diagnostica copertura xG nel feed importato (senza proxy)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureTeamStat
from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat

XG_MISSING_WARNING = "xG non disponibile nel feed importato."


def competition_has_xg_in_team_stats(db: Session, competition_id: int) -> bool:
    """True se almeno una riga fixture_team_stats ha xG valorizzato per il campionato."""
    rows = db.scalars(
        select(FixtureTeamStat)
        .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
        .where(Fixture.competition_id == int(competition_id))
        .limit(500),
    ).all()
    for st in rows:
        xg, _ = expected_goals_from_team_stat(st)
        if xg is not None:
            return True
    return False


def xg_coverage_summary(db: Session, competition_id: int) -> dict[str, object]:
    total = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureTeamStat)
            .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
            .where(Fixture.competition_id == int(competition_id)),
        )
        or 0,
    )
    if total == 0:
        return {"xg_feed_available": False, "xg_rows_with_value": 0, "xg_rows_total": 0, "xg_coverage_pct": 0.0}

    sample = db.scalars(
        select(FixtureTeamStat)
        .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
        .where(Fixture.competition_id == int(competition_id))
        .limit(2000),
    ).all()
    with_xg = sum(1 for st in sample if expected_goals_from_team_stat(st)[0] is not None)
    pct = round(100.0 * with_xg / max(len(sample), 1), 1)
    return {
        "xg_feed_available": with_xg > 0,
        "xg_rows_with_value": with_xg,
        "xg_rows_total": len(sample),
        "xg_coverage_pct": pct,
    }
