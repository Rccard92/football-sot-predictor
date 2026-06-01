"""Test runner analisi giornata — no_prediction senza eccezione."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.backtest.round_analysis_model_runner import RoundAnalysisModelRunner
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig


@patch.object(RoundAnalysisModelRunner, "_run_v21")
def test_run_for_fixture_isolates_model_errors(mock_v21):
    mock_v21.side_effect = RuntimeError("boom")
    runner = RoundAnalysisModelRunner()
    db = MagicMock()
    fx = MagicMock()
    fx.id = 1

    with patch.object(runner, "_run_v11_v20_style") as mock_v11:
        mock_v11.return_value = (
            {"status": "ok", "predicted_total_sot": 10.0, "label": "v1.1"},
            {},
        )
        models_json, _ = runner.run_for_fixture(
            db,
            fixture=fx,
            competition_id=1,
            mode="historical_official_xi",
            models=[
                "baseline_v1_1_sot",
                BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            ],
            lines=[8.5],
            cautious_drop_threshold=0.75,
            play_config=PlayAdviceConfig(),
            data_quality={"lineup": "ok"},
            actual_total=9,
        )

    assert "baseline_v1_1_sot" in models_json
    assert models_json["baseline_v1_1_sot"]["status"] == "ok"
    assert models_json[BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS]["status"] == "no_prediction"


@patch("app.services.backtest.round_analysis_model_runner.SotV21PointInTimePreviewService")
def test_v21_none_total_returns_no_prediction(mock_preview_cls):
    preview = MagicMock()
    preview.prediction.total_predicted_sot = None
    preview.prediction.home_predicted_sot = None
    preview.prediction.away_predicted_sot = None
    preview.home_prior_matches_count = 0
    preview.away_prior_matches_count = 0
    preview.warnings = []
    preview.home_trace.macros = []
    preview.away_trace.macros = []
    mock_preview_cls.return_value.build_preview.return_value = preview

    runner = RoundAnalysisModelRunner()
    block, _ = runner._run_v21(
        MagicMock(),
        fixture=MagicMock(id=1),
        competition_id=1,
        mode="historical_official_xi",
        lines=[8.5],
        cautious_drop_threshold=0.75,
        play_config=PlayAdviceConfig(),
        data_quality={},
        actual_total=5,
    )
    assert block["status"] == "no_prediction"
    assert block["reason"] == "INSUFFICIENT_HISTORY"
