"""Test componente forma recente v1.1."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.predictions_v11.recent_form_strict import compute_recent_form_component
from app.services.predictions_v10.v10_prior_context import V10PriorContext

LB_RECENT_OK: dict[str, float] = {
    "league_recent_avg_sot_for": 3.5,
    "league_recent_avg_sot_conceded": 3.4,
    "league_recent_avg_total_shots_for": 12.0,
    "league_recent_avg_total_shots_conceded": 11.5,
    "league_recent_avg_goals_for": 1.2,
}


def _stat(**kwargs):
    return SimpleNamespace(**kwargs)


def _fx(fid: int, kickoff: datetime, home: int = 10, away: int = 2, gh: int = 1, ga: int = 0):
    return SimpleNamespace(
        id=fid,
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        goals_home=gh,
        goals_away=ga,
        status="FT",
    )


def _ctx(
    team_id: int = 10,
    team_fixtures: list | None = None,
    opponent_id: int = 20,
    opponent_fixtures: list | None = None,
) -> V10PriorContext:
    team_fixtures = team_fixtures or []
    opponent_fixtures = opponent_fixtures or []
    stats_map: dict = {}
    for f in team_fixtures:
        stats_map[(int(f.id), team_id)] = _stat(
            shots_on_target=4,
            total_shots=12,
            shots_inside_box=6,
            shots_outside_box=3,
            blocked_shots=2,
            shots_off_target=5,
        )
    for f in opponent_fixtures:
        other = int(f.away_team_id) if int(f.home_team_id) == opponent_id else int(f.home_team_id)
        stats_map[(int(f.id), other)] = _stat(
            shots_on_target=4,
            total_shots=12,
            shots_inside_box=6,
            shots_outside_box=3,
            blocked_shots=2,
        )
    return V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=999,
        team_id=team_id,
        opponent_id=opponent_id,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=3.5,
        stats_map=stats_map,
        team_prior_count=len(team_fixtures),
        opponent_prior_count=len(opponent_fixtures),
        team_prior_fixtures=team_fixtures,
        opponent_prior_fixtures=opponent_fixtures,
        league_baselines={},
    )


def test_insufficient_recent_sample_short_history():
    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=10, away=90 + i) for i in range(1, 4)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=88 + i, away=20) for i in range(1, 7)]
    ctx = _ctx(team_fixtures=team_fx, opponent_fixtures=opp_fx)
    comp, _miss, status, _a, _b = compute_recent_form_component(
        ctx,
        team_fx,
        league_baselines={**LB_RECENT_OK},
    )
    assert comp is None
    assert status == "insufficient_recent_sample"


def test_missing_recent_league_baseline_keys():
    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=88 + i, away=20) for i in range(1, 7)]
    ctx = _ctx(team_fixtures=team_fx, opponent_fixtures=opp_fx)
    bad_lb = dict(LB_RECENT_OK)
    del bad_lb["league_recent_avg_goals_for"]
    comp, _miss, status, _a, _b = compute_recent_form_component(
        ctx,
        team_fx,
        league_baselines=bad_lb,
    )
    assert comp is None
    assert status == "missing_required_recent_league_baseline"


def test_ok_six_inputs_and_trend():
    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=88 + i, away=20) for i in range(1, 7)]
    ctx = _ctx(team_fixtures=team_fx, opponent_fixtures=opp_fx)
    comp, _miss, status, t_n, o_n = compute_recent_form_component(
        ctx,
        team_fx,
        league_baselines={**LB_RECENT_OK},
    )
    assert status == "ok"
    assert comp is not None
    assert t_n == 5 and o_n == 5
    assert len(comp["inputs"]) == 6
    keys = {str(x.get("key")) for x in comp["inputs"]}
    assert keys == {
        "recent_avg_sot_for",
        "recent_opponent_avg_sot_conceded",
        "recent_avg_total_shots_for",
        "recent_opponent_avg_total_shots_conceded",
        "recent_avg_goals_for",
        "recent_trend_vs_season",
    }
    trend_blob = next(b for b in comp["inputs"] if b.get("key") == "recent_trend_vs_season")
    assert trend_blob.get("sample_count") == 5


def test_v11_side_insufficient_recent_via_offensive_pipeline():
    from app.services.predictions_v11.offensive_production_strict import compute_v11_side

    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=10, away=90 + i) for i in range(1, 7)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=88 + i, away=20) for i in range(1, 4)]
    ctx = _ctx(team_fixtures=team_fx, opponent_fixtures=opp_fx)
    db = MagicMock()
    league_full = {
        "league_avg_sot_for": 3.5,
        "league_avg_total_shots_for": 12.0,
        "league_avg_inside_box_shots_for": 5.0,
        "league_avg_outside_box_shots_for": 4.0,
        "league_avg_blocked_shots_for": 2.0,
        "league_avg_shots_off_goal_for": 4.0,
        "league_avg_goals_for": 1.2,
        "league_avg_shot_accuracy": 0.32,
        "league_avg_sot_conceded": 3.5,
        "league_avg_total_shots_conceded": 12.0,
        "league_avg_inside_box_shots_conceded": 5.0,
        "league_avg_outside_box_shots_conceded": 4.0,
        "league_avg_blocked_shots_conceded": 2.0,
        "home_league_split_avg_sot_for": 3.5,
        "home_league_split_avg_sot_conceded": 3.4,
        "home_league_split_avg_total_shots_for": 12.0,
        "home_league_split_avg_total_shots_conceded": 11.5,
        "away_league_split_avg_sot_for": 3.2,
        "away_league_split_avg_sot_conceded": 3.3,
        "away_league_split_avg_total_shots_for": 11.0,
        "away_league_split_avg_total_shots_conceded": 11.2,
        **LB_RECENT_OK,
    }
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_v11_baselines_strict",
        return_value=league_full,
    ):
        result = compute_v11_side(db, ctx, team_fx)
    assert not result.valid
    assert result.formula_quality_status == "insufficient_recent_sample"
