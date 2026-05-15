"""Riepilogo copertura Player DB (sole letture)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Fixture,
    FixturePlayerStat,
    PlayerMatchStat,
    PlayerRegistry,
    PlayerSeasonProfile,
    PlayerSotProfile,
    PlayerTeamSeason,
)
from app.services.ingestion_service import IngestionService


def player_db_summary(db: Session, season_year: int) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season_year)
    except ValueError as exc:
        return {
            "status": "error",
            "season": season_year,
            "message": str(exc),
        }

    year = int(season_row.year)
    league_id = int(season_row.league_id)

    n_registry = int(db.scalar(select(func.count()).select_from(PlayerRegistry)) or 0)
    n_pts = int(
        db.scalar(
            select(func.count()).select_from(PlayerTeamSeason).where(
                PlayerTeamSeason.season == year,
                PlayerTeamSeason.league_id == league_id,
            ),
        )
        or 0,
    )
    n_pms = int(
        db.scalar(
            select(func.count()).select_from(PlayerMatchStat).where(
                PlayerMatchStat.season == year,
                PlayerMatchStat.league_id == league_id,
            ),
        )
        or 0,
    )
    n_psp = int(
        db.scalar(
            select(func.count()).select_from(PlayerSeasonProfile).where(
                PlayerSeasonProfile.season == year,
                PlayerSeasonProfile.league_id == league_id,
            ),
        )
        or 0,
    )
    n_fps = int(
        db.scalar(
            select(func.count())
            .select_from(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(Fixture.season_id == season_row.id),
        )
        or 0,
    )

    n_fps_api = int(
        db.scalar(
            select(func.count())
            .select_from(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(
                Fixture.season_id == season_row.id,
                FixturePlayerStat.api_player_id.isnot(None),
            ),
        )
        or 0,
    )

    n_profiles = int(
        db.scalar(
            select(func.count()).select_from(PlayerSotProfile).where(
                PlayerSotProfile.season_id == season_row.id,
            ),
        )
        or 0,
    )

    cov = round(100.0 * n_fps_api / n_fps, 2) if n_fps else 0.0

    return {
        "status": "success",
        "season": season_year,
        "player_registry_rows": n_registry,
        "player_team_seasons_rows": n_pts,
        "player_match_stats_rows": n_pms,
        "player_season_profiles_rows": n_psp,
        "fixture_player_stats_rows": n_fps,
        "fixture_player_stats_with_api_player_id": n_fps_api,
        "fixture_player_stats_api_id_coverage_pct": cov,
        "player_sot_profiles_rows": n_profiles,
    }
