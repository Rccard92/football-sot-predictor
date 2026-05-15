"""Baseline lega: league_recent_avg_goals_for deve essere presente nel dict restituito."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.predictions_v11.league_baselines_strict import compute_league_v11_baselines_strict


def _mk_fx(i: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=i,
        season_id=1,
        status="FT",
        kickoff_at=datetime(2025, 1, i, tzinfo=timezone.utc),
        home_team_id=1,
        away_team_id=2,
        goals_home=2,
        goals_away=1,
    )


def _mk_st(fid: int, tid: int) -> SimpleNamespace:
    return SimpleNamespace(
        fixture_id=fid,
        team_id=tid,
        shots_on_target=4,
        total_shots=10,
        shots_inside_box=3,
        shots_outside_box=2,
        blocked_shots=None,
        shots_off_goal=None,
        expected_goals=1.0,
        raw_json=None,
    )


def test_compute_league_v11_includes_league_recent_avg_goals_for():
    fxs = [_mk_fx(i) for i in range(1, 7)]
    stats: list[SimpleNamespace] = []
    for f in fxs:
        stats.append(_mk_st(int(f.id), 1))
        stats.append(_mk_st(int(f.id), 2))

    ncall = [0]

    def scalars(_sel):
        r = MagicMock()
        ncall[0] += 1
        r.all.return_value = fxs if ncall[0] == 1 else stats
        return r

    db = MagicMock()
    db.scalars = scalars

    out = compute_league_v11_baselines_strict(
        db,
        season_id=1,
        cutoff_kickoff=datetime(2025, 7, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=9999,
    )
    assert out["league_recent_avg_goals_for"] == 1.5
    assert out["league_recent_goals_baseline_team_count"] == 2.0
