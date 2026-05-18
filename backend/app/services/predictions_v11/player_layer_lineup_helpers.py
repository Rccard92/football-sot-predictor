"""Helper lineups ufficiali per Player layer v1.1 stage 7B (solo DB, nessuna API live)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureLineup, FixtureLineupPlayer, PlayerSeasonProfile
from app.services.predictions_v11.v11_shared import safe_float
from app.services.sot_feature_registry import V11_MIN_PLAYER_MINUTES, V11_TOP_PLAYERS_USED

TOP_SHOOTERS_TOTAL = 5
LINEUP_STARTERS_PROFILE_WARNING_THRESHOLD = 7
BENCH_PRESENCE_FACTOR = 0.35


def _float_from_decimal(v: Decimal | float | int | None) -> float | None:
    return safe_float(v)


def _is_eligible_profile(p: PlayerSeasonProfile) -> bool:
    mins = p.minutes_total
    if mins is None or float(mins) < V11_MIN_PLAYER_MINUTES:
        return False
    if p.reliability_score is None:
        return False
    if p.shots_on_per90 is None and p.shots_total_per90 is None:
        return False
    return True


def _sort_key_profile(p: PlayerSeasonProfile) -> tuple:
    impact = _float_from_decimal(p.shooting_impact_score)
    sot90 = _float_from_decimal(p.shots_on_per90)
    mins = _float_from_decimal(p.minutes_total)
    return (
        impact is None,
        -(impact or 0.0),
        -(sot90 or 0.0),
        -(mins or 0.0),
    )


def select_top_shooter_api_ids(
    profiles: dict[int, PlayerSeasonProfile],
    *,
    limit: int = TOP_SHOOTERS_TOTAL,
) -> list[int]:
    """Top shooter squadra (non limitati ai titolari) per shooting_impact / SOT90 / minuti."""
    eligible = [p for p in profiles.values() if _is_eligible_profile(p)]
    eligible.sort(key=_sort_key_profile)
    return [int(p.api_player_id) for p in eligible[:limit]]


def fixture_both_lineups_available(
    db: Session,
    *,
    fixture_id: int,
    home_team_id: int,
    away_team_id: int,
) -> bool:
    for team_id in (int(home_team_id), int(away_team_id)):
        lineup = db.scalar(
            select(FixtureLineup).where(
                FixtureLineup.fixture_id == int(fixture_id),
                FixtureLineup.team_id == int(team_id),
                FixtureLineup.is_available.is_(True),
            ),
        )
        if lineup is None:
            return False
        n_starters = db.scalar(
            select(func.count())
            .select_from(FixtureLineupPlayer)
            .where(
                FixtureLineupPlayer.fixture_lineup_id == int(lineup.id),
                FixtureLineupPlayer.is_starter.is_(True),
            ),
        )
        if not n_starters or int(n_starters) < 1:
            return False
    return True


def load_team_lineup_for_fixture(
    db: Session,
    *,
    fixture_id: int,
    team_id: int,
) -> FixtureLineup | None:
    return db.scalar(
        select(FixtureLineup).where(
            FixtureLineup.fixture_id == int(fixture_id),
            FixtureLineup.team_id == int(team_id),
            FixtureLineup.is_available.is_(True),
        ),
    )


def load_lineup_players_by_role(
    db: Session,
    *,
    fixture_lineup_id: int,
) -> tuple[list[FixtureLineupPlayer], list[FixtureLineupPlayer]]:
    players = db.scalars(
        select(FixtureLineupPlayer)
        .where(FixtureLineupPlayer.fixture_lineup_id == int(fixture_lineup_id))
        .order_by(FixtureLineupPlayer.is_starter.desc(), FixtureLineupPlayer.number.asc().nulls_last()),
    ).all()
    starters = [p for p in players if p.is_starter]
    bench = [p for p in players if p.is_substitute and not p.is_starter]
    return starters, bench


def _pack_shooter_entry(
    api_player_id: int,
    profiles: dict[int, PlayerSeasonProfile],
    *,
    role: str,
) -> dict[str, Any]:
    pr = profiles.get(int(api_player_id))
    return {
        "api_player_id": int(api_player_id),
        "role": role,
        "shots_on_per90": _float_from_decimal(pr.shots_on_per90) if pr else None,
        "shooting_impact_score": _float_from_decimal(pr.shooting_impact_score) if pr else None,
        "minutes_total": _float_from_decimal(pr.minutes_total) if pr else None,
    }


def classify_top_shooters_in_lineup(
    top_shooter_ids: list[int],
    starter_api_ids: set[int],
    bench_api_ids: set[int],
    profiles: dict[int, PlayerSeasonProfile],
) -> dict[str, Any]:
    starting: list[int] = []
    bench: list[int] = []
    missing: list[int] = []
    for apid in top_shooter_ids:
        if apid in starter_api_ids:
            starting.append(apid)
        elif apid in bench_api_ids:
            bench.append(apid)
        else:
            missing.append(apid)
    return {
        "top_shooters_total": TOP_SHOOTERS_TOTAL,
        "top_shooters_starting": len(starting),
        "top_shooters_on_bench": len(bench),
        "top_shooters_not_in_lineup": len(missing),
        "starting_top_shooters": [
            _pack_shooter_entry(i, profiles, role="starter") for i in starting
        ],
        "bench_top_shooters": [_pack_shooter_entry(i, profiles, role="bench") for i in bench],
        "missing_top_shooters_from_lineup": [
            _pack_shooter_entry(i, profiles, role="not_in_squad") for i in missing
        ],
    }


def lineup_presence_absence_signals(
    *,
    top_shooters_starting: int,
    top_shooters_on_bench: int,
    top_shooters_total: int = TOP_SHOOTERS_TOTAL,
) -> tuple[float, float]:
    total = max(int(top_shooters_total), 1)
    presence = float(top_shooters_starting) / float(total)
    penalty_signal = 1.0 - (
        (float(top_shooters_starting) + float(top_shooters_on_bench) * BENCH_PRESENCE_FACTOR)
        / float(total)
    )
    penalty_signal = max(0.0, min(1.0, penalty_signal))
    return presence, penalty_signal


def normalize_presence_signal(signal: float, league_avg_sot_for: float) -> float:
    return float(league_avg_sot_for) * (0.85 + float(signal) * 0.30)


def normalize_absence_signal(signal: float, league_avg_sot_for: float) -> float:
    capped = max(0.0, min(0.25, float(signal) * 0.25))
    return float(league_avg_sot_for) * (1.0 - capped)


def profile_map_for_team(
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
    return {int(p.api_player_id): p for p in rows}


def starter_has_offensive_profile(p: PlayerSeasonProfile | None) -> bool:
    if p is None:
        return False
    return p.shots_on_per90 is not None or p.shots_total_per90 is not None


def load_fixture_for_lineup(db: Session, fixture_id: int) -> Fixture | None:
    return db.get(Fixture, int(fixture_id))
