from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import (
    Fixture,
    FixtureLineup,
    FixtureProviderLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    IngestionRun,
    PlayerSeasonProfile,
    TeamSotPrediction,
    TrackedBettingPick,
)
from app.services.competition_service import CompetitionService
from app.services.next_round_selection import select_next_round_fixtures


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
    pred_by_model_rows = db.execute(
        select(TeamSotPrediction.model_version, func.count())
        .where(TeamSotPrediction.competition_id == comp.id)
        .group_by(TeamSotPrediction.model_version)
    ).all()
    predictions_by_model = {str(mv): int(cnt) for mv, cnt in pred_by_model_rows}
    lineups_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureLineup)
            .where(FixtureLineup.competition_id == comp.id)
        )
        or 0
    )
    sportapi_lineups_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureProviderLineup)
            .where(FixtureProviderLineup.competition_id == comp.id)
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

    mappings_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureProviderMapping)
            .where(FixtureProviderMapping.competition_id == comp.id)
        )
        or 0
    )

    all_upcoming = list(
        db.scalars(
            select(Fixture).where(
                Fixture.competition_id == comp.id,
                ~Fixture.status.in_(FINISHED_STATUSES),
            )
        ).all()
    )
    next_round_sel = select_next_round_fixtures(all_upcoming, limit=100, only_next_round=True)
    next_round_ids = [int(fx.id) for fx in next_round_sel.fixtures]
    next_round_fixture_count = len(next_round_ids)

    next_round_mappings_count = 0
    next_round_lineups_count = 0
    if next_round_ids:
        next_round_mappings_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderMapping)
                .where(
                    FixtureProviderMapping.competition_id == comp.id,
                    FixtureProviderMapping.fixture_id.in_(next_round_ids),
                )
            )
            or 0
        )
        next_round_lineups_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderLineup)
                .where(
                    FixtureProviderLineup.competition_id == comp.id,
                    FixtureProviderLineup.fixture_id.in_(next_round_ids),
                )
            )
            or 0
        )

    next_round_lineup_coverage_pct = round(
        100.0 * next_round_lineups_count / max(next_round_fixture_count, 1),
        1,
    )
    missing_mappings_next_round = max(next_round_fixture_count - next_round_mappings_count, 0)

    sportapi_rows = list(
        db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.competition_id == comp.id,
            )
        ).all()
    )
    confirmed_lineups_count = sum(1 for r in sportapi_rows if bool(r.confirmed))
    probable_lineups_count = len(sportapi_rows) - confirmed_lineups_count

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
        "predictions_by_model": predictions_by_model,
        "lineup_rows_count": lineups_count,
        "lineups_api_football_count": lineups_count,
        "sportapi_lineup_rows_count": sportapi_lineups_count,
        "lineups_sportapi_count": sportapi_lineups_count,
        "confirmed_lineups_count": confirmed_lineups_count,
        "probable_lineups_count": probable_lineups_count,
        "lineup_coverage_pct": lineup_coverage_pct,
        "sportapi_mappings_count": mappings_count,
        "missing_mappings": max(finished_count - mappings_count, 0),
        "next_round_fixture_count": next_round_fixture_count,
        "next_round_lineups_count": next_round_lineups_count,
        "next_round_sportapi_lineups_count": next_round_lineups_count,
        "next_round_lineup_coverage_pct": next_round_lineup_coverage_pct,
        "missing_mappings_next_round": missing_mappings_next_round,
        "tracked_picks_count": picks_count,
        "last_ingestion": {
            "source": last_ingestion.source if last_ingestion else None,
            "status": last_ingestion.status if last_ingestion else None,
            "started_at": last_ingestion.started_at.isoformat() if last_ingestion and last_ingestion.started_at else None,
            "records_processed": last_ingestion.records_processed if last_ingestion else None,
        },
    }
