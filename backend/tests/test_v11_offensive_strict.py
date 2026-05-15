"""Test produzione offensiva + blend 60/40 v1.1."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.predictions_v11.league_baselines_strict import MissingLeagueBaselineError
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.predictions_v10.v10_prior_context import V10PriorContext

LEAGUE_V11_MOCK = {
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


def test_insufficient_team_sample():
    fixtures = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 4)]
    opp = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=20, away=90 + i) for i in range(1, 7)]
    ctx = _ctx(team_fixtures=fixtures, opponent_fixtures=opp)
    db = MagicMock()
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_v11_baselines_strict",
        return_value=LEAGUE_V11_MOCK,
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
    opp = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=20, away=90 + i) for i in range(1, 7)]
    ctx = _ctx(team_fixtures=fixtures, opponent_fixtures=opp)
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
        stats_map={**ctx.stats_map, **stats_map},
        team_prior_count=ctx.team_prior_count,
        opponent_prior_count=ctx.opponent_prior_count,
        team_prior_fixtures=ctx.team_prior_fixtures,
        opponent_prior_fixtures=ctx.opponent_prior_fixtures,
        league_baselines=ctx.league_baselines,
    )
    db = MagicMock()
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_v11_baselines_strict",
        return_value=LEAGUE_V11_MOCK,
    ):
        result = compute_v11_side(db, ctx, fixtures)
    assert not result.valid
    assert result.formula_quality_status == "missing_required_data"
    keys = [m.get("feature_key") for m in result.missing_required_fields]
    assert "avg_inside_box_shots_for" in keys


def test_valid_blend_60_40():
    team_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc)) for i in range(1, 7)]
    opp_fx = [_fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=20, away=90 + i) for i in range(1, 7)]
    ctx = _ctx(team_fixtures=team_fx, opponent_fixtures=opp_fx)
    db = MagicMock()
    with patch(
        "app.services.predictions_v11.offensive_production_strict.compute_league_v11_baselines_strict",
        return_value=LEAGUE_V11_MOCK,
    ):
        result = compute_v11_side(db, ctx, team_fx)
    assert result.valid
    assert result.expected_sot is not None
    assert result.component is not None
    assert result.defensive_component is not None
    off_val = float(result.component["value"])
    def_val = float(result.defensive_component["value"])
    expected = round(off_val * 0.60 + def_val * 0.40, 2)
    assert result.expected_sot == pytest.approx(expected, rel=1e-4)
    assert result.raw_json["formula"]["terms_count"] == 2
    assert len(result.component["inputs"]) == 9
    assert len(result.defensive_component["inputs"]) == 6


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
