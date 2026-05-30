"""Baseline xG lega v2.1 scoped per competition_id con anti-leakage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureTeamStat
from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat
from app.services.sot_feature_math import fixture_key_before


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def latest_prior_kickoff(fixtures: list[Fixture]) -> datetime | None:
    """Kickoff più recente tra le fixture prior (anti-leakage window)."""
    if not fixtures:
        return None
    latest = max(fixtures, key=lambda f: (f.kickoff_at, int(f.id)))
    return latest.kickoff_at


def build_xg_leakage_trace(
    *,
    team_fixtures: list[Fixture],
    opp_fixtures: list[Fixture],
    team_sample_count: int | None,
    opp_sample_count: int | None,
) -> dict[str, Any]:
    """Metadata trace per audit xG: sample_count, latest_fixture_used_at, leakage_guard."""
    all_fx = list({id(f): f for f in team_fixtures + opp_fixtures}.values())
    latest = latest_prior_kickoff(all_fx)
    sample_count = max(int(team_sample_count or 0), int(opp_sample_count or 0)) or None
    return {
        "sample_count": sample_count,
        "latest_fixture_used_at": latest.isoformat() if latest is not None else None,
        "leakage_guard": True,
    }


def compute_v21_xg_league_baselines(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    competition_id: int,
) -> dict[str, Any]:
    """
    Medie lega xG for/conceded su fixture finite della competition prima del cutoff.
    Usa expected_goals_from_team_stat (colonna DB e/o raw_json statistics).
    """
    clauses = [
        Fixture.season_id == int(season_id),
        Fixture.competition_id == int(competition_id),
        Fixture.status.in_(FINISHED_STATUSES),
    ]
    fixtures = db.scalars(select(Fixture).where(*clauses)).all()
    eligible = [
        f
        for f in fixtures
        if fixture_key_before(f.kickoff_at, int(f.id), cutoff_kickoff, cutoff_fixture_id)
    ]
    if not eligible:
        return {
            "league_avg_xg_for": None,
            "league_avg_xg_conceded": None,
            "league_avg_sot_for": None,
            "league_avg_sot_conceded": None,
            "sample_fixtures": 0,
            "sample_team_stat_rows": 0,
            "latest_fixture_used_at": None,
            "leakage_guard": True,
        }

    fx_ids = [int(f.id) for f in eligible]
    stats = db.scalars(
        select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fx_ids)),
    ).all()
    stats_by_fx_team: dict[tuple[int, int], FixtureTeamStat] = {
        (int(st.fixture_id), int(st.team_id)): st for st in stats
    }

    xg_for_vals: list[float] = []
    xg_conceded_vals: list[float] = []
    sot_for_vals: list[float] = []
    sot_conceded_vals: list[float] = []

    for st in stats:
        xg_for, _ = expected_goals_from_team_stat(st)
        if xg_for is not None:
            xg_for_vals.append(float(xg_for))
        if st.shots_on_target is not None:
            sot_for_vals.append(float(st.shots_on_target))

    for f in eligible:
        hid, aid = int(f.home_team_id), int(f.away_team_id)
        home_st = stats_by_fx_team.get((int(f.id), hid))
        away_st = stats_by_fx_team.get((int(f.id), aid))
        if home_st and away_st:
            xg_c_away, _ = expected_goals_from_team_stat(away_st)
            if xg_c_away is not None:
                xg_conceded_vals.append(float(xg_c_away))
            xg_c_home, _ = expected_goals_from_team_stat(home_st)
            if xg_c_home is not None:
                xg_conceded_vals.append(float(xg_c_home))
            if away_st.shots_on_target is not None:
                sot_conceded_vals.append(float(away_st.shots_on_target))
            if home_st.shots_on_target is not None:
                sot_conceded_vals.append(float(home_st.shots_on_target))

    latest = latest_prior_kickoff(eligible)
    return {
        "league_avg_xg_for": _mean(xg_for_vals),
        "league_avg_xg_conceded": _mean(xg_conceded_vals),
        "league_avg_sot_for": _mean(sot_for_vals),
        "league_avg_sot_conceded": _mean(sot_conceded_vals),
        "sample_fixtures": len(eligible),
        "sample_team_stat_rows": len(xg_for_vals),
        "latest_fixture_used_at": latest.isoformat() if latest is not None else None,
        "leakage_guard": True,
    }
