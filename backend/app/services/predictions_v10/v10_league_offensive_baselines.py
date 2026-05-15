"""
Medie lega per normalizzazione componente offensiva v1.0 (anti-leakage).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureTeamStat
from app.services.sot_feature_math import fixture_key_before

PRUDENTIAL_LEAGUE_SOT = 3.5
PRUDENTIAL_LEAGUE_SHOTS = 12.0
PRUDENTIAL_LEAGUE_GOALS = 1.1
PRUDENTIAL_LEAGUE_ACCURACY = 0.32


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def compute_league_offensive_baselines(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> dict[str, float | None]:
    """Medie lega su tutte le righe team-stats delle partite finite prima del cutoff."""
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
        return _empty_baselines_with_prudential()

    fx_ids = [int(f.id) for f in eligible]
    stats = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fx_ids))).all()
    if not stats:
        return _empty_baselines_with_prudential()

    sot_vals: list[float] = []
    shots_vals: list[float] = []
    inside_vals: list[float] = []
    outside_vals: list[float] = []
    blocked_vals: list[float] = []
    off_goal_vals: list[float] = []
    goals_vals: list[float] = []
    accuracy_vals: list[float] = []

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
        if st.shots_off_goal is not None:
            off_goal_vals.append(float(st.shots_off_goal))
        gf = goals_by_fx_team.get((int(st.fixture_id), int(st.team_id)))
        if gf is not None:
            goals_vals.append(gf)
        if (
            st.shots_on_target is not None
            and st.total_shots is not None
            and float(st.total_shots) > 0
        ):
            accuracy_vals.append(float(st.shots_on_target) / float(st.total_shots))

    league_sot = _mean(sot_vals) or PRUDENTIAL_LEAGUE_SOT
    league_shots = _mean(shots_vals) or PRUDENTIAL_LEAGUE_SHOTS
    league_goals = _mean(goals_vals) or PRUDENTIAL_LEAGUE_GOALS
    league_acc = _mean(accuracy_vals) or PRUDENTIAL_LEAGUE_ACCURACY

    return {
        "league_avg_sot_for": league_sot,
        "league_avg_total_shots_for": league_shots,
        "league_avg_inside_box_shots_for": _mean(inside_vals) or league_sot,
        "league_avg_outside_box_shots_for": _mean(outside_vals) or league_sot,
        "league_avg_blocked_shots_for": _mean(blocked_vals) or league_sot,
        "league_avg_shots_off_goal_for": _mean(off_goal_vals) or league_sot,
        "league_avg_goals_for": league_goals,
        "league_avg_shot_accuracy": league_acc,
        "sample_team_stat_rows": len(stats),
        "sample_fixtures": len(eligible),
    }


def _empty_baselines_with_prudential() -> dict[str, float | None]:
    return {
        "league_avg_sot_for": PRUDENTIAL_LEAGUE_SOT,
        "league_avg_total_shots_for": PRUDENTIAL_LEAGUE_SHOTS,
        "league_avg_inside_box_shots_for": PRUDENTIAL_LEAGUE_SOT,
        "league_avg_outside_box_shots_for": PRUDENTIAL_LEAGUE_SOT,
        "league_avg_blocked_shots_for": PRUDENTIAL_LEAGUE_SOT,
        "league_avg_shots_off_goal_for": PRUDENTIAL_LEAGUE_SOT,
        "league_avg_goals_for": PRUDENTIAL_LEAGUE_GOALS,
        "league_avg_shot_accuracy": PRUDENTIAL_LEAGUE_ACCURACY,
        "sample_team_stat_rows": 0,
        "sample_fixtures": 0,
    }
