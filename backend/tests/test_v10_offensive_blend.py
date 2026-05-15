"""Test componente Produzione offensiva composita v1.0."""

from datetime import datetime, timezone
import pytest

from app.models import Fixture, FixtureTeamStat
from app.services.predictions_v10.offensive_production_blend import (
    OFFENSIVE_INTERNAL_WEIGHTS,
    INPUT_ORDER,
    compute_offensive_production_component,
    offensive_inputs_as_map,
)
from app.services.predictions_v10.v10_prior_context import V10PriorContext


def _make_ctx(*, league_baselines: dict | None = None) -> V10PriorContext:
    lb = league_baselines or {
        "league_avg_sot_for": 3.5,
        "league_avg_total_shots_for": 12.0,
        "league_avg_inside_box_shots_for": 7.0,
        "league_avg_outside_box_shots_for": 5.0,
        "league_avg_blocked_shots_for": 4.0,
        "league_avg_shots_off_goal_for": 4.5,
        "league_avg_goals_for": 1.2,
        "league_avg_shot_accuracy": 0.32,
    }
    return V10PriorContext(
        season_id=1,
        cutoff_kickoff=datetime(2025, 6, 1, tzinfo=timezone.utc),
        cutoff_fixture_id=100,
        team_id=10,
        opponent_id=20,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=3.5,
        stats_map={},
        team_prior_count=3,
        opponent_prior_count=3,
        team_prior_fixtures=[],
        opponent_prior_fixtures=[],
        league_baselines=lb,
    )


def _fixture_and_stats(team_id: int = 10, *, sot: int = 4, shots: int = 12) -> tuple[Fixture, FixtureTeamStat]:
    fx = Fixture(
        id=1,
        season_id=1,
        home_team_id=team_id,
        away_team_id=99,
        kickoff_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
        status="FT",
        goals_home=2,
        goals_away=0,
    )
    st = FixtureTeamStat(
        fixture_id=1,
        team_id=team_id,
        shots_on_target=sot,
        total_shots=shots,
        shots_inside_box=7,
        shots_outside_box=5,
        blocked_shots=3,
        shots_off_goal=4,
    )
    return fx, st


def test_internal_weights_sum_to_one():
    assert pytest.approx(sum(OFFENSIVE_INTERNAL_WEIGHTS.values()), rel=1e-6) == 1.0
    assert len(INPUT_ORDER) == 9


def test_offensive_component_nine_inputs_list():
    fx, st = _fixture_and_stats()
    ctx = _make_ctx()
    ctx.stats_map[(1, 10)] = st
    comp = compute_offensive_production_component(ctx, [fx])
    assert comp["key"] == "offensive_production_component"
    assert comp["label"] == "Produzione offensiva composita"
    assert isinstance(comp["inputs"], list)
    assert len(comp["inputs"]) == 9
    assert comp["quality"]["inputs_total"] == 9
    keys = {x["key"] for x in comp["inputs"]}
    assert keys == set(INPUT_ORDER)
    for inp in comp["inputs"]:
        assert "raw_value" in inp
        assert "normalized_value" in inp
        assert "internal_weight" in inp
        assert "internal_contribution" in inp
        assert inp.get("source_path")
    assert comp["weight_in_final_formula"] == 0.30
    assert comp["contribution_in_final_formula"] == pytest.approx(float(comp["value"]) * 0.30, rel=1e-3)


def test_offensive_inputs_as_map_from_list():
    comp = {
        "inputs": [
            {"key": "avg_sot_for", "normalized_value": 3.9},
            {"key": "avg_total_shots_for", "normalized_value": 3.7},
        ],
    }
    m = offensive_inputs_as_map(comp)
    assert m["avg_sot_for"]["normalized_value"] == 3.9


def test_trend_uses_last5_minus_season():
    fixtures = []
    stats_map = {}
    for i, sot in enumerate([3, 3, 3, 3, 5], start=1):
        fx = Fixture(
            id=i,
            season_id=1,
            home_team_id=10,
            away_team_id=99,
            kickoff_at=datetime(2025, 4, i, tzinfo=timezone.utc),
            status="FT",
            goals_home=1,
            goals_away=0,
        )
        fixtures.append(fx)
        stats_map[(i, 10)] = FixtureTeamStat(
            fixture_id=i,
            team_id=10,
            shots_on_target=sot,
            total_shots=10,
            shots_inside_box=5,
            shots_outside_box=3,
            blocked_shots=2,
            shots_off_goal=2,
        )
    ctx = _make_ctx()
    ctx.stats_map = stats_map
    comp = compute_offensive_production_component(ctx, fixtures)
    trend_inp = next(x for x in comp["inputs"] if x["key"] == "offensive_trend")
    assert trend_inp["raw_value"] == pytest.approx(2.0, rel=1e-3)
