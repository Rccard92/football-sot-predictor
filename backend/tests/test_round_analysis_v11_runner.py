"""Test runner v1.1 in-memory (Step I)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.v11_round_analysis_preview import V11RoundAnalysisPreviewService


@patch("app.services.backtest.v11_round_analysis_preview.compute_v11_side")
@patch("app.services.backtest.v11_round_analysis_preview.build_prior_context")
def test_v11_preview_no_team_sot_predictions_write(mock_ctx, mock_compute):
    db = MagicMock()
    fx = MagicMock()
    fx.id = 1
    fx.home_team_id = 10
    fx.away_team_id = 20
    fx.competition_id = 2

    ctx = MagicMock()
    ctx.team_prior_fixtures = []
    ctx.team_prior_count = 12
    ctx.opponent_prior_count = 11
    mock_ctx.return_value = ctx

    side = MagicMock()
    side.valid = True
    side.expected_sot = 5.5
    side.formula_quality_status = "ok"
    side.raw_json = {"components": {}}
    mock_compute.return_value = side

    with patch(
        "app.services.backtest.v11_round_analysis_preview.fixture_both_lineups_available",
        return_value=True,
    ):
        out = V11RoundAnalysisPreviewService().build_fixture_model(
            db,
            fixture=fx,
            competition_id=2,
            data_quality={"lineup": "ok", "mapping": "ok"},
        )

    assert out["predicted_total_sot"] == 11.0
    db.add.assert_not_called()
