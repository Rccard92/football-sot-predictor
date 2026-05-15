"""Test produzione offensiva strict v1.1."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.predictions_v11.league_baselines_strict import MissingLeagueBaselineError
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.predictions_v10.v10_prior_context import V10PriorContext


def _stat(**kwargs):
    return SimpleNamespace(**kwargs)


def _fx(fid: int, kickoff: datetime, home: int = 1, away: int = 2, gh: int = 1, ga: int = 0):
    return SimpleNamespace(
        id=fid,
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        goals_home=gh,
        goals_away=ga,
        status="FT",
    )


def _ctx(team_id: int = 10, fixtures: list | None = None) -> V10PriorContext:
    fixtures = fixtures or []
    stats_map = {}
    for f in fixtures:
        stats_map[(int(f.id), team_id)] = _stat(
            shots_on_target=4,
            total_shots=12,
            shots_inside_box=6,
            shots_outside_box=3,
            blocked_shots=2,
            shots_off_target=5,
        )
    return V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=999,
        team_id=team_id,
        opponent_id=20,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=3.5,
        stats_map=stats_map,
        team_prior_count=len(fixtures),
        opponent_prior_count=0,
        team_prior_fixtures=fixtures,
        opponent_prior_fixtures=[],
        league_baselines={},
    )


def test_insufficient_sample():
    fixtures = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 4)]
    ctx = _ctx(fixtures=fixtures)
    db = MagicMock()
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_offensive_baselines_strict",
        return_value={
            "league_avg_sot_for": 3.5,
            "league_avg_total_shots_for": 12.0,
            "league_avg_inside_box_shots_for": 5.0,
            "league_avg_outside_box_shots_for": 4.0,
            "league_avg_blocked_shots_for": 2.0,
            "league_avg_shots_off_goal_for": 4.0,
            "league_avg_goals_for": 1.2,
            "league_avg_shot_accuracy": 0.32,
        },
    ):
        result = compute_v11_side(db, ctx, fixtures)
    assert not result.valid
    assert result.formula_quality_status == "insufficient_sample"


def test_missing_inside_box_data():
    fixtures = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 7)]
    stats_map = {}
    for f in fixtures:
        stats_map[(int(f.id), 10)] = _stat(
            shots_on_target=4,
            total_shots=12,
            shots_inside_box=None,
            shots_outside_box=3,
            blocked_shots=2,
            shots_off_target=5,
        )
    ctx = _ctx(fixtures=fixtures)
    ctx = V10PriorContext(
        season_id=ctx.season_id,
        cutoff_kickoff=ctx.cutoff_kickoff,
        cutoff_fixture_id=ctx.cutoff_fixture_id,
        team_id=ctx.team_id,
        opponent_id=ctx.opponent_id,
        is_home=ctx.is_home,
        team_priors=ctx.team_priors,
        opponent_priors=ctx.opponent_priors,
        league_avg_sot=ctx.league_avg_sot,
        stats_map=stats_map,
        team_prior_count=ctx.team_prior_count,
        opponent_prior_count=ctx.opponent_prior_count,
        team_prior_fixtures=ctx.team_prior_fixtures,
        opponent_prior_fixtures=ctx.opponent_prior_fixtures,
        league_baselines=ctx.league_baselines,
    )
    db = MagicMock()
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_offensive_baselines_strict",
        return_value={
            "league_avg_sot_for": 3.5,
            "league_avg_total_shots_for": 12.0,
            "league_avg_inside_box_shots_for": 5.0,
            "league_avg_outside_box_shots_for": 4.0,
            "league_avg_blocked_shots_for": 2.0,
            "league_avg_shots_off_goal_for": 4.0,
            "league_avg_goals_for": 1.2,
            "league_avg_shot_accuracy": 0.32,
        },
    ):
        result = compute_v11_side(db, ctx, fixtures)
    assert not result.valid
    assert result.formula_quality_status == "missing_required_data"
    keys = [m.get("feature_key") for m in result.missing_required_fields]
    assert "avg_inside_box_shots_for" in keys


def test_valid_blend_nine_inputs_no_fallback():
    fixtures = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 7)]
    ctx = _ctx(fixtures=fixtures)
    db = MagicMock()
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_offensive_baselines_strict",
        return_value={
            "league_avg_sot_for": 3.5,
            "league_avg_total_shots_for": 12.0,
            "league_avg_inside_box_shots_for": 5.0,
            "league_avg_outside_box_shots_for": 4.0,
            "league_avg_blocked_shots_for": 2.0,
            "league_avg_shots_off_goal_for": 4.0,
            "league_avg_goals_for": 1.2,
            "league_avg_shot_accuracy": 0.32,
        },
    ):
        result = compute_v11_side(db, ctx, fixtures)
    assert result.valid
    assert result.expected_sot is not None
    comp = result.component
    assert comp is not None
    inputs = comp.get("inputs") or []
    assert len(inputs) == 9
    assert all(not inp.get("fallback_used") for inp in inputs)
    assert comp["quality"]["fallback_count"] == 0
    wsum = sum(float(inp["internal_weight"]) for inp in inputs)
    assert wsum == pytest.approx(1.0, rel=1e-6)


def test_league_baseline_missing_raises():
    from app.services.predictions_v11.league_baselines_strict import compute_league_offensive_baselines_strict

    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with pytest.raises(MissingLeagueBaselineError):
        compute_league_offensive_baselines_strict(
            db,
            season_id=1,
            cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
            cutoff_fixture_id=1,
        )
