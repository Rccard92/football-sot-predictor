"""Health read-only per Player DB (match stats + season profiles)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fixture, PlayerMatchStat, PlayerRegistry, PlayerSeasonProfile, PlayerTeamSeason, Team
from app.services.ingestion_service import IngestionService

_MATCH_COVERAGE_COLS = (
    "minutes",
    "shots_total",
    "shots_on",
    "rating",
)

_PROFILE_COVERAGE_COLS = (
    "shots_on_per90",
    "shots_total_per90",
    "team_sot_share",
    "team_shots_share",
    "avg_rating",
    "recent_minutes_last5",
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
        coverage = {c: 0.0 for c in _MATCH_COVERAGE_COLS}
    else:
        for col in _MATCH_COVERAGE_COLS:
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


def player_season_profiles_health_summary(db: Session, season_year: int) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season_year)
    except ValueError as exc:
        return {"status": "error", "season": season_year, "message": str(exc)}

    y = int(season_row.year)
    lid = int(season_row.league_id)

    base_filter = (
        PlayerSeasonProfile.season == y,
        PlayerSeasonProfile.league_id == lid,
    )

    player_season_profiles_total = int(
        db.scalar(
            select(func.count()).select_from(PlayerSeasonProfile).where(*base_filter),
        )
        or 0,
    )

    profiles_with_shooting_impact = int(
        db.scalar(
            select(func.count()).select_from(PlayerSeasonProfile).where(
                *base_filter,
                PlayerSeasonProfile.shooting_impact_score.isnot(None),
            ),
        )
        or 0,
    )

    profiles_with_reliability_score = int(
        db.scalar(
            select(func.count()).select_from(PlayerSeasonProfile).where(
                *base_filter,
                PlayerSeasonProfile.reliability_score.isnot(None),
            ),
        )
        or 0,
    )

    profiles_coverage: dict[str, float] = {}
    if player_season_profiles_total == 0:
        profiles_coverage = {c: 0.0 for c in _PROFILE_COVERAGE_COLS}
    else:
        for col in _PROFILE_COVERAGE_COLS:
            col_attr = getattr(PlayerSeasonProfile, col)
            with_val = int(
                db.scalar(
                    select(func.count()).select_from(PlayerSeasonProfile).where(
                        *base_filter,
                        col_attr.isnot(None),
                    ),
                )
                or 0,
            )
            profiles_coverage[col] = round(100.0 * with_val / player_season_profiles_total, 2)

    top_10_shooting_impact = _top_profiles_list(
        db,
        y,
        lid,
        order_col=PlayerSeasonProfile.shooting_impact_score,
        require_not_null=PlayerSeasonProfile.shooting_impact_score,
        limit=10,
    )
    top_10_sot_per90 = _top_profiles_list(
        db,
        y,
        lid,
        order_col=PlayerSeasonProfile.shots_on_per90,
        require_not_null=PlayerSeasonProfile.shots_on_per90,
        limit=10,
    )

    return {
        "player_season_profiles_total": player_season_profiles_total,
        "profiles_with_shooting_impact": profiles_with_shooting_impact,
        "profiles_with_reliability_score": profiles_with_reliability_score,
        "profiles_coverage": profiles_coverage,
        "top_10_shooting_impact": top_10_shooting_impact,
        "top_10_sot_per90": top_10_sot_per90,
    }


def _top_profiles_list(
    db: Session,
    year: int,
    league_id: int,
    *,
    order_col: Any,
    require_not_null: Any,
    limit: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(PlayerSeasonProfile, PlayerRegistry, Team)
        .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
        .outerjoin(Team, Team.id == PlayerSeasonProfile.team_id)
        .where(
            PlayerSeasonProfile.season == year,
            PlayerSeasonProfile.league_id == league_id,
            require_not_null.isnot(None),
        )
        .order_by(order_col.desc())
        .limit(limit),
    ).all()

    out: list[dict[str, Any]] = []
    for pr, reg, tm in rows:
        out.append(
            {
                "player_name": reg.name,
                "team_name": tm.name if tm else None,
                "api_player_id": int(pr.api_player_id),
                "api_team_id": int(pr.api_team_id),
                "shots_on_per90": float(pr.shots_on_per90) if pr.shots_on_per90 is not None else None,
                "shots_total_per90": float(pr.shots_total_per90) if pr.shots_total_per90 is not None else None,
                "team_sot_share": float(pr.team_sot_share) if pr.team_sot_share is not None else None,
                "shooting_impact_score": float(pr.shooting_impact_score)
                if pr.shooting_impact_score is not None
                else None,
                "reliability_score": pr.reliability_score,
            },
        )
    return out


def player_db_health_summary(db: Session, season_year: int) -> dict[str, Any]:
    match_part = player_match_db_health_summary(db, season_year)
    if match_part.get("status") == "error":
        return match_part

    profiles_part = player_season_profiles_health_summary(db, season_year)
    if profiles_part.get("status") == "error":
        return profiles_part

    merged = {**match_part, **profiles_part}
    return merged
