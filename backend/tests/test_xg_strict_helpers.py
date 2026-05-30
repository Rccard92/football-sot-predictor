"""Test helper xG strict condiviso."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.predictions_common.xg_strict_helpers import build_strict_xg_snapshot


def _team_stat(**kwargs) -> SimpleNamespace:
    base = dict(
        expected_goals=1.2,
        raw_json=None,
        shots_on_target=4,
        total_shots=12,
        shots_inside_box=6,
        shots_outside_box=3,
        blocked_shots=2,
        shots_off_goal=5,
        ball_possession_pct=None,
        total_passes=None,
        accurate_passes=None,
        pass_accuracy_pct=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _prior(team_xg: float, opp_xg: float, n: int = 6):
    team_fixtures = []
    opp_fixtures = []
    stats_map = {}
    ko = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i in range(n):
        fid = i + 1
        team_fixtures.append(
            SimpleNamespace(id=fid, home_team_id=1, away_team_id=99, kickoff_at=ko, goals_home=1, goals_away=0),
        )
        stats_map[(fid, 1)] = _team_stat(expected_goals=team_xg)
        ofid = 100 + i
        opp_fixtures.append(
            SimpleNamespace(id=ofid, home_team_id=88, away_team_id=2, kickoff_at=ko, goals_home=0, goals_away=1),
        )
        stats_map[(ofid, 88)] = _team_stat(expected_goals=opp_xg)
    return team_fixtures, opp_fixtures, stats_map


def test_build_strict_xg_snapshot_matches_v11_logic():
    team_fx, opp_fx, stats_map = _prior(1.5, 1.3, n=6)
    snap = build_strict_xg_snapshot(
        prior_fixtures=team_fx,
        opponent_prior_fixtures=opp_fx,
        stats_map=stats_map,
        team_id=1,
        opponent_id=2,
        league_baselines={
            "league_avg_xg_for": 1.25,
            "league_avg_xg_conceded": 1.20,
            "league_avg_sot_for": 4.0,
            "league_avg_sot_conceded": 4.0,
        },
    )
    assert snap.status == "ok"
    assert snap.avg_xg_for == 1.5
    assert snap.opponent_avg_xg_conceded == 1.3
    assert snap.team_xg_delta_vs_league == 0.25
    assert snap.opponent_xg_conceded_delta_vs_league == pytest.approx(0.1)
    assert snap.xg_adjustment_pct is not None
    assert snap.leakage_guard is True
    assert snap.team_xg_n == 6
    assert snap.opp_xg_n == 6


def test_build_strict_xg_insufficient_sample_still_computes():
    team_fx, opp_fx, stats_map = _prior(1.4, 1.2, n=3)
    snap = build_strict_xg_snapshot(
        prior_fixtures=team_fx,
        opponent_prior_fixtures=opp_fx,
        stats_map=stats_map,
        team_id=1,
        opponent_id=2,
        league_baselines={
            "league_avg_xg_for": 1.25,
            "league_avg_xg_conceded": 1.20,
            "league_avg_sot_for": 4.0,
            "league_avg_sot_conceded": 4.0,
        },
    )
    assert snap.status == "insufficient_xg_sample"
    assert snap.avg_xg_for == pytest.approx(1.4)
    assert snap.warnings
