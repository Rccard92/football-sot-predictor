"""
Medie lega per normalizzazione v1.1 — nessun fallback prudenziale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureTeamStat
from app.services.sot_feature_math import fixture_key_before

REQUIRED_LEAGUE_OFFENSIVE_KEYS: tuple[str, ...] = (
    "league_avg_sot_for",
    "league_avg_total_shots_for",
    "league_avg_inside_box_shots_for",
    "league_avg_outside_box_shots_for",
    "league_avg_blocked_shots_for",
    "league_avg_shots_off_goal_for",
    "league_avg_goals_for",
    "league_avg_shot_accuracy",
)

REQUIRED_LEAGUE_DEFENSIVE_KEYS: tuple[str, ...] = (
    "league_avg_sot_conceded",
    "league_avg_total_shots_conceded",
    "league_avg_inside_box_shots_conceded",
    "league_avg_outside_box_shots_conceded",
    "league_avg_blocked_shots_conceded",
)

REQUIRED_LEAGUE_SPLIT_HOME_KEYS: tuple[str, ...] = (
    "home_league_split_avg_sot_for",
    "home_league_split_avg_sot_conceded",
    "home_league_split_avg_total_shots_for",
    "home_league_split_avg_total_shots_conceded",
)

REQUIRED_LEAGUE_SPLIT_AWAY_KEYS: tuple[str, ...] = (
    "away_league_split_avg_sot_for",
    "away_league_split_avg_sot_conceded",
    "away_league_split_avg_total_shots_for",
    "away_league_split_avg_total_shots_conceded",
)

REQUIRED_LEAGUE_KEYS: tuple[str, ...] = (
    REQUIRED_LEAGUE_OFFENSIVE_KEYS
    + REQUIRED_LEAGUE_DEFENSIVE_KEYS
    + REQUIRED_LEAGUE_SPLIT_HOME_KEYS
    + REQUIRED_LEAGUE_SPLIT_AWAY_KEYS
)


class MissingLeagueBaselineError(Exception):
    def __init__(self, missing_keys: list[str], *, sample_fixtures: int = 0) -> None:
        self.missing_keys = missing_keys
        self.sample_fixtures = sample_fixtures
        super().__init__(f"missing_required_league_baseline: {missing_keys}")


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _validate_keys(baselines: dict[str, float | None], keys: tuple[str, ...], sample_fixtures: int) -> dict[str, float]:
    missing: list[str] = []
    for key in keys:
        v = baselines.get(key)
        if v is None or float(v) <= 0:
            missing.append(key)
    if missing:
        raise MissingLeagueBaselineError(missing, sample_fixtures=sample_fixtures)
    return {k: float(baselines[k]) for k in keys}  # type: ignore[arg-type]


def split_league_baselines_for_context(full: dict[str, float], *, is_home_context: bool) -> dict[str, float]:
    """Mappa chiavi league_split_* per il contesto casa/trasferta della predizione."""
    prefix = "home_" if is_home_context else "away_"
    return {
        "league_split_avg_sot_for": float(full[f"{prefix}league_split_avg_sot_for"]),
        "league_split_avg_sot_conceded": float(full[f"{prefix}league_split_avg_sot_conceded"]),
        "league_split_avg_total_shots_for": float(full[f"{prefix}league_split_avg_total_shots_for"]),
        "league_split_avg_total_shots_conceded": float(full[f"{prefix}league_split_avg_total_shots_conceded"]),
    }


def compute_league_v11_baselines_strict(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> dict[str, float]:
    """Una scansione DB: medie lega offensive (for) e defensive (concessi)."""
    fixtures = db.scalars(
        select(Fixture).where(
            Fixture.season_id == int(season_id),
            Fixture.status.in_(FINISHED_STATUSES),
        ),
    ).all()
    eligible = [
        f
        for f in fixtures
        if fixture_key_before(f.kickoff_at, int(f.id), cutoff_kickoff, cutoff_fixture_id)
    ]
    if not eligible:
        raise MissingLeagueBaselineError(list(REQUIRED_LEAGUE_KEYS), sample_fixtures=0)

    fx_ids = [int(f.id) for f in eligible]
    stats = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fx_ids))).all()
    if not stats:
        raise MissingLeagueBaselineError(list(REQUIRED_LEAGUE_KEYS), sample_fixtures=len(eligible))

    stats_by_fx_team: dict[tuple[int, int], FixtureTeamStat] = {
        (int(st.fixture_id), int(st.team_id)): st for st in stats
    }

    sot_vals: list[float] = []
    shots_vals: list[float] = []
    inside_vals: list[float] = []
    outside_vals: list[float] = []
    blocked_vals: list[float] = []
    off_goal_vals: list[float] = []
    goals_vals: list[float] = []
    accuracy_vals: list[float] = []

    sot_conceded_vals: list[float] = []
    shots_conceded_vals: list[float] = []
    inside_conceded_vals: list[float] = []
    outside_conceded_vals: list[float] = []
    blocked_conceded_vals: list[float] = []

    home_sot_for_vals: list[float] = []
    home_sot_conceded_vals: list[float] = []
    home_shots_for_vals: list[float] = []
    home_shots_conceded_vals: list[float] = []
    away_sot_for_vals: list[float] = []
    away_sot_conceded_vals: list[float] = []
    away_shots_for_vals: list[float] = []
    away_shots_conceded_vals: list[float] = []

    goals_by_fx_team: dict[tuple[int, int], float] = {}
    for f in eligible:
        if f.goals_home is not None:
            goals_by_fx_team[(int(f.id), int(f.home_team_id))] = float(f.goals_home)
        if f.goals_away is not None:
            goals_by_fx_team[(int(f.id), int(f.away_team_id))] = float(f.goals_away)

    for st in stats:
        if st.shots_on_target is not None:
            sot_vals.append(float(st.shots_on_target))
        if st.total_shots is not None:
            shots_vals.append(float(st.total_shots))
        if st.shots_inside_box is not None:
            inside_vals.append(float(st.shots_inside_box))
        if st.shots_outside_box is not None:
            outside_vals.append(float(st.shots_outside_box))
        if st.blocked_shots is not None:
            blocked_vals.append(float(st.blocked_shots))
        if st.shots_off_target is not None:
            off_goal_vals.append(float(st.shots_off_target))
        gf = goals_by_fx_team.get((int(st.fixture_id), int(st.team_id)))
        if gf is not None:
            goals_vals.append(gf)
        if (
            st.shots_on_target is not None
            and st.total_shots is not None
            and float(st.total_shots) > 0
        ):
            accuracy_vals.append(float(st.shots_on_target) / float(st.total_shots))

    for f in eligible:
        hid, aid = int(f.home_team_id), int(f.away_team_id)
        home_st = stats_by_fx_team.get((int(f.id), hid))
        away_st = stats_by_fx_team.get((int(f.id), aid))
        if home_st and away_st:
            if away_st.shots_on_target is not None:
                sot_conceded_vals.append(float(away_st.shots_on_target))
            if away_st.total_shots is not None:
                shots_conceded_vals.append(float(away_st.total_shots))
            if away_st.shots_inside_box is not None:
                inside_conceded_vals.append(float(away_st.shots_inside_box))
            if away_st.shots_outside_box is not None:
                outside_conceded_vals.append(float(away_st.shots_outside_box))
            if away_st.blocked_shots is not None:
                blocked_conceded_vals.append(float(away_st.blocked_shots))
            if home_st.shots_on_target is not None:
                sot_conceded_vals.append(float(home_st.shots_on_target))
            if home_st.total_shots is not None:
                shots_conceded_vals.append(float(home_st.total_shots))
            if home_st.shots_inside_box is not None:
                inside_conceded_vals.append(float(home_st.shots_inside_box))
            if home_st.shots_outside_box is not None:
                outside_conceded_vals.append(float(home_st.shots_outside_box))
            if home_st.blocked_shots is not None:
                blocked_conceded_vals.append(float(home_st.blocked_shots))
            if home_st.shots_on_target is not None:
                home_sot_for_vals.append(float(home_st.shots_on_target))
            if away_st.shots_on_target is not None:
                home_sot_conceded_vals.append(float(away_st.shots_on_target))
            if home_st.total_shots is not None:
                home_shots_for_vals.append(float(home_st.total_shots))
            if away_st.total_shots is not None:
                home_shots_conceded_vals.append(float(away_st.total_shots))
            if away_st.shots_on_target is not None:
                away_sot_for_vals.append(float(away_st.shots_on_target))
            if home_st.shots_on_target is not None:
                away_sot_conceded_vals.append(float(home_st.shots_on_target))
            if away_st.total_shots is not None:
                away_shots_for_vals.append(float(away_st.total_shots))
            if home_st.total_shots is not None:
                away_shots_conceded_vals.append(float(home_st.total_shots))

    baselines: dict[str, float | None] = {
        "league_avg_sot_for": _mean(sot_vals),
        "league_avg_total_shots_for": _mean(shots_vals),
        "league_avg_inside_box_shots_for": _mean(inside_vals),
        "league_avg_outside_box_shots_for": _mean(outside_vals),
        "league_avg_blocked_shots_for": _mean(blocked_vals),
        "league_avg_shots_off_goal_for": _mean(off_goal_vals),
        "league_avg_goals_for": _mean(goals_vals),
        "league_avg_shot_accuracy": _mean(accuracy_vals),
        "league_avg_sot_conceded": _mean(sot_conceded_vals),
        "league_avg_total_shots_conceded": _mean(shots_conceded_vals),
        "league_avg_inside_box_shots_conceded": _mean(inside_conceded_vals),
        "league_avg_outside_box_shots_conceded": _mean(outside_conceded_vals),
        "league_avg_blocked_shots_conceded": _mean(blocked_conceded_vals),
        "home_league_split_avg_sot_for": _mean(home_sot_for_vals),
        "home_league_split_avg_sot_conceded": _mean(home_sot_conceded_vals),
        "home_league_split_avg_total_shots_for": _mean(home_shots_for_vals),
        "home_league_split_avg_total_shots_conceded": _mean(home_shots_conceded_vals),
        "away_league_split_avg_sot_for": _mean(away_sot_for_vals),
        "away_league_split_avg_sot_conceded": _mean(away_sot_conceded_vals),
        "away_league_split_avg_total_shots_for": _mean(away_shots_for_vals),
        "away_league_split_avg_total_shots_conceded": _mean(away_shots_conceded_vals),
        "sample_team_stat_rows": len(stats),
        "sample_fixtures": len(eligible),
    }

    out = _validate_keys(baselines, REQUIRED_LEAGUE_KEYS, len(eligible))
    out["sample_team_stat_rows"] = float(baselines["sample_team_stat_rows"])
    out["sample_fixtures"] = float(baselines["sample_fixtures"])
    return out


def compute_league_offensive_baselines_strict(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> dict[str, float]:
    full = compute_league_v11_baselines_strict(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
    )
    out = {k: full[k] for k in REQUIRED_LEAGUE_OFFENSIVE_KEYS}
    out["sample_team_stat_rows"] = full["sample_team_stat_rows"]
    out["sample_fixtures"] = full["sample_fixtures"]
    return out


def compute_league_defensive_conceded_baselines_strict(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> dict[str, float]:
    full = compute_league_v11_baselines_strict(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
    )
    return {k: full[k] for k in REQUIRED_LEAGUE_DEFENSIVE_KEYS}
