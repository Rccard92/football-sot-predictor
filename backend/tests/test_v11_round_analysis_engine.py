"""Test motore v1.1 Round Analysis (contesto produzione)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.v11_round_analysis_engine import (
    build_v11_prior_context,
    predict_v11_side_for_team,
)


@patch("app.services.backtest.v11_round_analysis_engine.compute_v11_side")
@patch("app.services.backtest.v11_round_analysis_engine.build_prior_context")
def test_predict_v11_side_uses_production_context(mock_build, mock_compute):
    db = MagicMock()
    fx = MagicMock()
    fx.id = 92
    ctx = MagicMock()
    ctx.team_prior_fixtures = []
    mock_build.return_value = ctx
    side = MagicMock()
    mock_compute.return_value = side

    result, returned_ctx = predict_v11_side_for_team(
        db,
        fx,
        team_id=1,
        opponent_id=2,
        competition_id=10,
    )

    assert result is side
    assert returned_ctx is ctx
    mock_build.assert_called_once_with(
        db,
        fx,
        team_id=1,
        opponent_id=2,
        competition_id=10,
    )
    assert "competition_scoped_only" not in mock_build.call_args.kwargs
    assert "strict_kickoff_only" not in mock_build.call_args.kwargs
    mock_compute.assert_called_once_with(
        db,
        ctx,
        ctx.team_prior_fixtures,
        allow_split_fallback=True,
    )


@patch("app.services.backtest.v11_round_analysis_engine.build_prior_context")
def test_build_v11_prior_context_no_pit_flags(mock_build):
    db = MagicMock()
    fx = MagicMock()
    build_v11_prior_context(db, fx, team_id=1, opponent_id=2, competition_id=3)
    mock_build.assert_called_once()
    assert "competition_scoped_only" not in mock_build.call_args.kwargs
