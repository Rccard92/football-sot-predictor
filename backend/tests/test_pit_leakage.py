"""Test anti-leakage strict cutoff PIT (backtest)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.backtest.pit_leakage import (
    compute_leakage_guard,
    is_prior_fixture,
    pit_strict_kickoff_before,
)
from app.services.backtest.point_in_time_context_service import PointInTimeContextService

_T = datetime(2025, 12, 14, 14, 0, tzinfo=timezone.utc)
_EARLIER = datetime(2025, 12, 13, 20, 45, tzinfo=timezone.utc)


def test_pit_strict_kickoff_before_same_time_excluded():
    assert pit_strict_kickoff_before(_EARLIER, _T) is True
    assert pit_strict_kickoff_before(_T, _T) is False
    assert pit_strict_kickoff_before(_T, _EARLIER) is False


def test_is_prior_fixture_strict_excludes_same_kickoff_lower_id():
    assert is_prior_fixture(_T, 100, _T, 148, strict_kickoff_only=True) is False
    assert is_prior_fixture(_EARLIER, 100, _T, 148, strict_kickoff_only=True) is True


def test_is_prior_fixture_default_allows_same_kickoff_lower_id():
    assert is_prior_fixture(_T, 100, _T, 148, strict_kickoff_only=False) is True
    assert is_prior_fixture(_T, 148, _T, 148, strict_kickoff_only=False) is False


def test_compute_leakage_guard():
    assert compute_leakage_guard(_T, _EARLIER) is True
    assert compute_leakage_guard(_T, _T) is False
    assert compute_leakage_guard(_T, None) is True
    assert compute_leakage_guard(_T, _EARLIER, _T) is False


@patch("app.services.backtest.point_in_time_context_service.build_prior_context")
@patch("app.services.backtest.point_in_time_context_service.compute_v21_xg_league_baselines")
@patch("app.services.backtest.point_in_time_context_service.compute_league_offensive_baselines")
@patch("app.services.backtest.point_in_time_context_service._league_prior_fixtures")
def test_pit_context_passes_strict_kickoff_only(
    mock_league_prior,
    mock_off_lb,
    mock_xg_lb,
    mock_build_prior,
):
    from app.services.predictions_v10.v10_prior_context import V10PriorContext

    db = MagicMock()
    comp = MagicMock()
    comp.key = "serie_a"
    comp.name = "Serie A"
    fixture = MagicMock()
    fixture.id = 148
    fixture.competition_id = 1
    fixture.home_team_id = 10
    fixture.away_team_id = 11
    fixture.kickoff_at = _T
    fixture.round = "Regular Season - 15"
    fixture.status = "FT"
    fixture.season_id = 1
    fixture.goals_home = 1
    fixture.goals_away = 0

    home_team = MagicMock()
    home_team.name = "Fiorentina"
    away_team = MagicMock()
    away_team.name = "Hellas Verona"

    db.get.side_effect = lambda model, pk: {
        1: comp,
        148: fixture,
        10: home_team,
        11: away_team,
    }.get(pk)

    prior_fx = MagicMock()
    prior_fx.id = 120
    prior_fx.kickoff_at = _EARLIER
    prior_fx.home_team_id = 10
    prior_fx.away_team_id = 99

    mock_league_prior.return_value = [prior_fx]

    prior_ctx = V10PriorContext(
        season_id=1,
        cutoff_kickoff=_T,
        cutoff_fixture_id=148,
        team_id=10,
        opponent_id=11,
        is_home=True,
        team_priors=[],
        opponent_priors=[],
        league_avg_sot=4.0,
        stats_map={},
        team_prior_count=1,
        opponent_prior_count=1,
        team_prior_fixtures=[prior_fx],
        opponent_prior_fixtures=[prior_fx],
        league_baselines={},
    )
    mock_build_prior.return_value = prior_ctx
    mock_xg_lb.return_value = {
        "league_avg_xg_for": 1.2,
        "league_avg_xg_conceded": 1.1,
        "league_avg_sot_for": 4.5,
        "league_avg_sot_conceded": 4.2,
        "sample_fixtures": 1,
        "sample_team_stat_rows": 2,
        "latest_fixture_used_at": _EARLIER.isoformat(),
    }
    mock_off_lb.return_value = {"league_avg_sot_for": 4.5}

    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None

    ctx = PointInTimeContextService().build_sot_context(
        db,
        competition_id=1,
        fixture_id=148,
        mode="pre_lineup",
    )

    assert mock_build_prior.call_count == 2
    for call in mock_build_prior.call_args_list:
        assert call.kwargs["strict_kickoff_only"] is True
    assert mock_xg_lb.call_args.kwargs["strict_kickoff_only"] is True
    assert mock_off_lb.call_args.kwargs["strict_kickoff_only"] is True
    assert ctx.latest_fixture_used_at == _EARLIER
    assert ctx.latest_fixture_used_at < ctx.cutoff_time
    assert ctx.leakage_guard is True
    assert "possible_leakage" not in ctx.warnings
