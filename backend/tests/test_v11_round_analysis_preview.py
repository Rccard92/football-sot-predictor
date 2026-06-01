"""Test preview v1.1 Round Analysis — trace e contesto PIT."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.v11_round_analysis_preview import V11RoundAnalysisPreviewService


@patch("app.services.backtest.v11_round_analysis_preview.fixture_both_lineups_available", return_value=True)
@patch("app.services.backtest.v11_round_analysis_preview.compute_v11_side")
@patch("app.services.backtest.v11_round_analysis_preview.build_prior_context")
@patch("app.services.backtest.v11_round_analysis_preview.count_league_baseline_eligible_fixtures", return_value=50)
@patch("app.services.backtest.v11_round_analysis_preview.resolve_season_id_for_round_analysis", return_value=(5, {}))
def test_build_fixture_model_uses_competition_scoped_context(
    mock_resolve,
    mock_league_count,
    mock_ctx,
    mock_compute,
    mock_lineups,
):
    db = MagicMock()
    fx = MagicMock()
    fx.id = 92
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = MagicMock()
    fx.kickoff_at.isoformat.return_value = "2025-01-01T15:00:00"

    ctx = MagicMock()
    ctx.team_prior_count = 9
    ctx.opponent_prior_count = 9
    ctx.season_id = 5
    mock_ctx.return_value = ctx

    side = MagicMock()
    side.valid = True
    side.expected_sot = 5.0
    side.formula_quality_status = "ok"
    side.raw_json = {"components": {}}
    mock_compute.return_value = side

    out = V11RoundAnalysisPreviewService().build_fixture_model(
        db,
        fixture=fx,
        competition_id=1,
        data_quality={},
    )

    assert mock_ctx.call_count == 2
    for call in mock_ctx.call_args_list:
        assert call.kwargs.get("competition_scoped_only") is True
        assert call.kwargs.get("strict_kickoff_only") is True
    assert out["predicted_total_sot"] == 10.0
    trace = out["_meta"]["trace_summary"]
    assert trace["fixture_id"] == 92
    assert "missing_fields" in trace
