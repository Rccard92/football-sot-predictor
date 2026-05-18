"""Audit read-only formazioni ufficiali per fixture."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, FixtureLineup, FixtureLineupPlayer, PlayerSeasonProfile, Season, Team
from app.services.predictions_v11.player_layer_lineup_helpers import select_top_shooter_api_ids
from app.services.sot_feature_registry import V11_MIN_PLAYER_MINUTES

QUALITY_BLOCK: dict[str, Any] = {
    "source": "fixture_lineups",
    "api_live_call": False,
    "model_impact": True,
    "note": (
        "Lineups ufficiali usate dal Player layer (baseline_v1_1_sot) in modalità lineup-adjusted "
        "quando disponibili per casa e trasferta. Nessuna API live in generazione predizioni."
    ),
}

NOT_AVAILABLE_MESSAGE = (
    "Formazioni ufficiali non ancora disponibili nel DB. "
    "Esegui Aggiorna formazioni ufficiali vicino al match."
)


def _float_or_none(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    return float(v)


def _eligible_profile(p: PlayerSeasonProfile) -> bool:
    if p.reliability_score is None:
        return False
    mins = p.minutes_total
    if mins is None or float(mins) < V11_MIN_PLAYER_MINUTES:
        return False
    if p.shots_on_per90 is None and p.shots_total_per90 is None:
        return False
    return True


def _profile_map_for_team(
    db: Session,
    *,
    season_year: int,
    league_id: int,
    api_team_id: int,
) -> dict[int, PlayerSeasonProfile]:
    rows = db.scalars(
        select(PlayerSeasonProfile).where(
            PlayerSeasonProfile.season == int(season_year),
            PlayerSeasonProfile.league_id == int(league_id),
            PlayerSeasonProfile.api_team_id == int(api_team_id),
        ),
    ).all()
    out: dict[int, PlayerSeasonProfile] = {}
    for p in rows:
        out[int(p.api_player_id)] = p
    return out


def _pack_player_row(
    lp: FixtureLineupPlayer,
    profile: PlayerSeasonProfile | None,
    *,
    is_top_shooter: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "api_player_id": lp.api_player_id,
        "player_name": lp.player_name,
        "number": lp.number,
        "position": lp.position,
        "grid": lp.grid,
        "is_starter": lp.is_starter,
        "is_substitute": lp.is_substitute,
        "is_top_shooter_starter": is_top_shooter,
        "shots_on_per90": None,
        "shots_total_per90": None,
        "shooting_impact_score": None,
        "reliability_score": None,
    }
    if profile is not None:
        row["shots_on_per90"] = _float_or_none(profile.shots_on_per90)
        row["shots_total_per90"] = _float_or_none(profile.shots_total_per90)
        row["shooting_impact_score"] = _float_or_none(profile.shooting_impact_score)
        row["reliability_score"] = int(profile.reliability_score) if profile.reliability_score is not None else None
    return row


def _pack_team_side(
    db: Session,
    *,
    lineup: FixtureLineup,
    season_year: int,
    league_id: int,
) -> dict[str, Any]:
    team = lineup.team
    profiles = _profile_map_for_team(
        db,
        season_year=season_year,
        league_id=league_id,
        api_team_id=int(lineup.api_team_id or team.api_team_id),
    )
    players = db.scalars(
        select(FixtureLineupPlayer)
        .where(FixtureLineupPlayer.fixture_lineup_id == int(lineup.id))
        .order_by(FixtureLineupPlayer.is_starter.desc(), FixtureLineupPlayer.number.asc().nulls_last()),
    ).all()
    starters_raw = [p for p in players if p.is_starter]
    subs_raw = [p for p in players if p.is_substitute and not p.is_starter]

    top_ids = set(select_top_shooter_api_ids(profiles))
    starters: list[dict[str, Any]] = []
    for lp in starters_raw:
        apid = lp.api_player_id
        is_top = int(apid) in top_ids if apid is not None else False
        starters.append(
            _pack_player_row(lp, profiles.get(int(apid)) if apid is not None else None, is_top_shooter=is_top),
        )

    substitutes: list[dict[str, Any]] = []
    for lp in subs_raw:
        apid = lp.api_player_id
        pr = profiles.get(int(apid)) if apid is not None else None
        substitutes.append(_pack_player_row(lp, pr, is_top_shooter=False))

    return {
        "team_name": team.name if team else str(lineup.team_id),
        "formation": lineup.formation,
        "coach_name": lineup.coach_name,
        "starters": starters,
        "substitutes": substitutes,
    }


def build_fixture_lineups_debug(db: Session, fixture_id: int) -> dict[str, Any]:
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {
            "status": "error",
            "fixture_id": int(fixture_id),
            "message": "Fixture non trovata",
        }

    season = db.get(Season, int(fx.season_id))
    season_year = int(season.year) if season else 0
    league_id = int(fx.league_id)

    home_lineup = db.scalar(
        select(FixtureLineup)
        .options(joinedload(FixtureLineup.team))
        .where(
            FixtureLineup.fixture_id == int(fx.id),
            FixtureLineup.team_id == int(fx.home_team_id),
            FixtureLineup.is_available.is_(True),
        ),
    )
    away_lineup = db.scalar(
        select(FixtureLineup)
        .options(joinedload(FixtureLineup.team))
        .where(
            FixtureLineup.fixture_id == int(fx.id),
            FixtureLineup.team_id == int(fx.away_team_id),
            FixtureLineup.is_available.is_(True),
        ),
    )

    if home_lineup is None or away_lineup is None:
        return {
            "status": "not_available_yet",
            "fixture_id": int(fixture_id),
            "lineups_available": False,
            "message": NOT_AVAILABLE_MESSAGE,
        }

    return {
        "status": "success",
        "fixture_id": int(fixture_id),
        "lineups_available": True,
        "home": _pack_team_side(db, lineup=home_lineup, season_year=season_year, league_id=league_id),
        "away": _pack_team_side(db, lineup=away_lineup, season_year=season_year, league_id=league_id),
        "quality": dict(QUALITY_BLOCK),
    }
