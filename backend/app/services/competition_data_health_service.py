from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import (
    Competition,
    Fixture,
    FixtureLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    IngestionRun,
    PlayerSeasonProfile,
    TeamSotPrediction,
    TrackedBettingPick,
)
from app.services.competition_service import CompetitionService


def build_competition_data_health(db: Session, competition_id: int) -> dict[str, Any]:
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)

    fixture_count = int(
        db.scalar(select(func.count()).select_from(Fixture).where(Fixture.competition_id == comp.id)) or 0
    )
    finished_count = int(
        db.scalar(
            select(func.count())
            .select_from(Fixture)
            .where(Fixture.competition_id == comp.id, Fixture.status.in_(tuple(FINISHED_STATUSES)))
        )
        or 0
    )
    team_stats_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureTeamStat)
            .where(FixtureTeamStat.competition_id == comp.id)
        )
        or 0
    )
    profiles_count = int(
        db.scalar(
            select(func.count())
            .select_from(PlayerSeasonProfile)
            .where(PlayerSeasonProfile.competition_id == comp.id)
        )
        or 0
    )
    predictions_count = int(
        db.scalar(
            select(func.count())
            .select_from(TeamSotPrediction)
            .where(TeamSotPrediction.competition_id == comp.id)
        )
        or 0
    )
    lineups_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureLineup)
            .where(FixtureLineup.competition_id == comp.id)
        )
        or 0
    )
    mappings_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureProviderMapping)
            .where(FixtureProviderMapping.competition_id == comp.id)
        )
        or 0
    )
    picks_count = int(
        db.scalar(
            select(func.count())
            .select_from(TrackedBettingPick)
            .where(TrackedBettingPick.competition_id == comp.id)
        )
        or 0
    )
    teams_count = int(
        db.scalar(
            select(func.count(func.distinct(Fixture.home_team_id)))
            .select_from(Fixture)
            .where(Fixture.competition_id == comp.id)
        )
        or 0
    )
    last_ingestion = db.scalar(
        select(IngestionRun)
        .where(IngestionRun.competition_id == comp.id)
        .order_by(IngestionRun.started_at.desc().nulls_last(), IngestionRun.id.desc())
    )

    lineup_coverage_pct = round(100.0 * lineups_count / max(finished_count * 2, 1), 1)

    return {
        "competition_id": comp.id,
        "competition_key": comp.key,
        "competition_name": comp.name,
        "season": comp.season,
        "fixture_count": fixture_count,
        "finished_fixture_count": finished_count,
        "teams_count": teams_count,
        "player_profiles_count": profiles_count,
        "team_stats_count": team_stats_count,
        "predictions_count": predictions_count,
        "lineup_rows_count": lineups_count,
        "lineup_coverage_pct": lineup_coverage_pct,
        "sportapi_mappings_count": mappings_count,
        "missing_mappings": max(finished_count - mappings_count, 0),
        "tracked_picks_count": picks_count,
        "last_ingestion": {
            "source": last_ingestion.source if last_ingestion else None,
            "status": last_ingestion.status if last_ingestion else None,
            "started_at": last_ingestion.started_at.isoformat() if last_ingestion and last_ingestion.started_at else None,
            "records_processed": last_ingestion.records_processed if last_ingestion else None,
        },
    }
