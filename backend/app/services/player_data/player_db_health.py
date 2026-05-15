"""Health read-only per Player DB (match stats layer)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerMatchStat, PlayerRegistry, PlayerTeamSeason
from app.services.ingestion_service import IngestionService

_COVERAGE_COLS = (
    "minutes",
    "shots_total",
    "shots_on",
    "rating",
)


def player_match_db_health_summary(db: Session, season_year: int) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season_year)
    except ValueError as exc:
        return {"status": "error", "season": season_year, "message": str(exc)}

    y = int(season_row.year)
    lid = int(season_row.league_id)

    players_total = int(db.scalar(select(func.count()).select_from(PlayerRegistry)) or 0)
    player_team_seasons_total = int(
        db.scalar(
            select(func.count()).select_from(PlayerTeamSeason).where(
                PlayerTeamSeason.season == y,
                PlayerTeamSeason.league_id == lid,
            ),
        )
        or 0,
    )

    player_match_stats_total = int(
        db.scalar(
            select(func.count()).select_from(PlayerMatchStat).where(
                PlayerMatchStat.season == y,
                PlayerMatchStat.league_id == lid,
            ),
        )
        or 0,
    )

    fixtures_with_player_stats = int(
        db.scalar(
            select(func.count()).select_from(
                select(PlayerMatchStat.fixture_id)
                .where(
                    PlayerMatchStat.season == y,
                    PlayerMatchStat.league_id == lid,
                )
                .distinct()
                .subquery(),
            ),
        )
        or 0,
    )

    latest = db.execute(
        select(Fixture.id, Fixture.api_fixture_id, Fixture.kickoff_at)
        .join(PlayerMatchStat, PlayerMatchStat.fixture_id == Fixture.id)
        .where(PlayerMatchStat.season == y, PlayerMatchStat.league_id == lid)
        .order_by(Fixture.kickoff_at.desc())
        .limit(1),
    ).first()

    latest_imported_fixture: dict[str, Any] | None = None
    if latest:
        latest_imported_fixture = {
            "fixture_id": latest.id,
            "api_fixture_id": int(latest.api_fixture_id),
            "kickoff_at": latest.kickoff_at.isoformat() if latest.kickoff_at else None,
        }

    coverage: dict[str, float] = {}
    if player_match_stats_total == 0:
        coverage = {c: 0.0 for c in _COVERAGE_COLS}
    else:
        for col in _COVERAGE_COLS:
            col_attr = getattr(PlayerMatchStat, col)
            with_val = int(
                db.scalar(
                    select(func.count()).select_from(PlayerMatchStat).where(
                        PlayerMatchStat.season == y,
                        PlayerMatchStat.league_id == lid,
                        col_attr.isnot(None),
                    ),
                )
                or 0,
            )
            coverage[col] = round(100.0 * with_val / player_match_stats_total, 2)

    return {
        "status": "success",
        "season": season_year,
        "players_total": players_total,
        "player_team_seasons_total": player_team_seasons_total,
        "player_match_stats_total": player_match_stats_total,
        "fixtures_with_player_stats": fixtures_with_player_stats,
        "latest_imported_fixture": latest_imported_fixture,
        "coverage": coverage,
    }
