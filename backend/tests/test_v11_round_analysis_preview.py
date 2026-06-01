"""Test preview v1.1 Round Analysis — motore produzione."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.v11_round_analysis_preview import V11RoundAnalysisPreviewService


@patch("app.services.backtest.v11_round_analysis_preview.fixture_both_lineups_available", return_value=True)
@patch("app.services.backtest.v11_round_analysis_preview.predict_v11_side_for_team")
@patch("app.services.backtest.v11_round_analysis_preview.count_league_baseline_eligible_fixtures", return_value=50)
@patch("app.services.backtest.v11_round_analysis_preview.resolve_season_id_for_round_analysis", return_value=(5, {}))
def test_build_fixture_model_uses_production_engine(
    mock_resolve,
    mock_league_count,
    mock_predict,
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
    ctx.season_id = 5

    side = MagicMock()
    side.valid = True
    side.expected_sot = 5.0
    side.formula_quality_status = "ok"
    side.raw_json = {"components": {}}
    mock_predict.return_value = (side, ctx)

    out = V11RoundAnalysisPreviewService().build_fixture_model(
        db,
        fixture=fx,
        competition_id=1,
        data_quality={},
    )

    assert mock_predict.call_count == 2
    assert out["predicted_total_sot"] == 10.0
    trace = out["_meta"]["trace_summary"]
    assert trace["fixture_id"] == 92
    assert trace["formula_inputs"]["context_mode"] == "production_v11"
    assert "missing_fields" in trace
