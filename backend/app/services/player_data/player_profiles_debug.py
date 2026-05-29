"""Profili giocatore per fixture (audit read-only, nessuna API esterna)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, PlayerRegistry, PlayerSeasonProfile, PlayerTeamSeason, Team
from app.services.ingestion_service import IngestionService

SUPPORTED_SORTS = frozenset({"shooting_impact_score_desc"})
PROFILE_LIMIT_MAX = 100

QUALITY_BLOCK: dict[str, Any] = {
    "source": "player_season_profiles",
    "api_live_call": False,
    "model_impact": False,
    "note": "Dati mostrati solo per audit. Non ancora applicati alla formula baseline_v1_1_sot.",
}


def _float_or_none(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _int_or_none(value: int | None) -> int | None:
    if value is None:
        return None
    return int(value)


def profile_sort_key(row: dict[str, Any]) -> tuple:
    """Chiave ordinamento: impact desc (null last), poi sot/90, poi minuti."""
    impact = row.get("shooting_impact_score")
    sot90 = row.get("shots_on_per90")
    minutes = row.get("minutes_total")
    impact_key = (-impact if impact is not None else float("inf"))
    sot_key = -(sot90 if sot90 is not None else float("-inf"))
    min_key = -(minutes if minutes is not None else float("-inf"))
    return (impact_key, sot_key, min_key)


def sort_player_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=profile_sort_key)


def _pack_player_row(
    profile: PlayerSeasonProfile,
    registry: PlayerRegistry,
    position: str | None,
) -> dict[str, Any]:
    return {
        "player_id": str(profile.player_id),
        "api_player_id": int(profile.api_player_id),
        "name": registry.name,
        "position": position,
        "matches_played": _int_or_none(profile.matches_played),
        "minutes_total": _float_or_none(profile.minutes_total),
        "recent_minutes_last5": _float_or_none(profile.recent_minutes_last5),
        "shots_total": _int_or_none(profile.shots_total),
        "shots_on": _int_or_none(profile.shots_on),
        "shots_total_per90": _float_or_none(profile.shots_total_per90),
        "shots_on_per90": _float_or_none(profile.shots_on_per90),
        "shot_accuracy": _float_or_none(profile.shot_accuracy),
        "team_shots_share": _float_or_none(profile.team_shots_share),
        "team_sot_share": _float_or_none(profile.team_sot_share),
        "avg_rating": _float_or_none(profile.avg_rating),
        "shooting_impact_score": _float_or_none(profile.shooting_impact_score),
        "reliability_score": _int_or_none(profile.reliability_score),
    }


def _load_team_profiles(
    db: Session,
    *,
    season: int,
    league_id: int,
    api_team_id: int,
    team_id: int | None,
    team_name: str,
    limit: int,
    competition_id: int | None = None,
) -> dict[str, Any]:
    base_filter: list = [
        PlayerSeasonProfile.season == season,
        PlayerSeasonProfile.league_id == league_id,
        PlayerSeasonProfile.api_team_id == api_team_id,
    ]
    if competition_id is not None:
        base_filter.append(PlayerSeasonProfile.competition_id == int(competition_id))

    profiles_total = int(
        db.scalar(
            select(func.count()).select_from(PlayerSeasonProfile).where(*base_filter),
        )
        or 0,
    )

    rows = db.execute(
        select(PlayerSeasonProfile, PlayerRegistry, PlayerTeamSeason.position)
        .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
        .outerjoin(
            PlayerTeamSeason,
            (PlayerTeamSeason.season == PlayerSeasonProfile.season)
            & (PlayerTeamSeason.league_id == PlayerSeasonProfile.league_id)
            & (PlayerTeamSeason.api_team_id == PlayerSeasonProfile.api_team_id)
            & (PlayerTeamSeason.api_player_id == PlayerSeasonProfile.api_player_id),
        )
        .where(*base_filter)
        .order_by(
            PlayerSeasonProfile.shooting_impact_score.desc().nulls_last(),
            PlayerSeasonProfile.shots_on_per90.desc().nulls_last(),
            PlayerSeasonProfile.minutes_total.desc().nulls_last(),
        )
        .limit(limit),
    ).all()

    players = [_pack_player_row(pr, reg, pos) for pr, reg, pos in rows]

    return {
        "team_id": team_id,
        "api_team_id": int(api_team_id),
        "team_name": team_name,
        "profiles_total": profiles_total,
        "profiles_returned": len(players),
        "players": players,
    }


def build_fixture_player_profiles_debug(
    db: Session,
    fixture_id: int,
    *,
    season_year: int | None = None,
    limit: int = 15,
    sort: str = "shooting_impact_score_desc",
) -> dict[str, Any]:
    if sort not in SUPPORTED_SORTS:
        return {
            "status": "error",
            "message": f"sort non supportato: {sort}",
            "fixture_id": int(fixture_id),
            "supported_sorts": sorted(SUPPORTED_SORTS),
        }

    fx = db.scalar(
        select(Fixture)
        .options(
            joinedload(Fixture.home_team),
            joinedload(Fixture.away_team),
            joinedload(Fixture.season),
        )
        .where(Fixture.id == int(fixture_id)),
    )

    if fx is None:
        return {
            "status": "error",
            "message": "Fixture non trovata",
            "fixture_id": int(fixture_id),
        }

    if season_year is not None:
        try:
            season_row = IngestionService()._serie_a_season_row(db, season_year)
            year = int(season_row.year)
            league_id = int(season_row.league_id)
        except ValueError as exc:
            return {
                "status": "error",
                "message": str(exc),
                "fixture_id": int(fixture_id),
                "season": season_year,
            }
    else:
        if fx.season is None:
            return {
                "status": "error",
                "message": "Stagione fixture non disponibile",
                "fixture_id": int(fixture_id),
            }
        year = int(fx.season.year)
        league_id = int(fx.league_id)

    home_team: Team = fx.home_team
    away_team: Team = fx.away_team

    comp_id = int(fx.competition_id) if fx.competition_id is not None else None

    home_payload = _load_team_profiles(
        db,
        season=year,
        league_id=league_id,
        api_team_id=int(home_team.api_team_id),
        team_id=int(home_team.id),
        team_name=home_team.name,
        limit=limit,
        competition_id=comp_id,
    )
    away_payload = _load_team_profiles(
        db,
        season=year,
        league_id=league_id,
        api_team_id=int(away_team.api_team_id),
        team_id=int(away_team.id),
        team_name=away_team.name,
        limit=limit,
        competition_id=comp_id,
    )

    return {
        "status": "success",
        "fixture_id": int(fixture_id),
        "season": year,
        "home": home_payload,
        "away": away_payload,
        "quality": dict(QUALITY_BLOCK),
    }
