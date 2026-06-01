"""Test adapter isolati Round Analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.backtest.adapters.sot_v11_round_analysis_adapter import (
    ERR_INSUFFICIENT_PRIOR,
    ERR_PREDICTION_INCOMPLETE,
    SotV11RoundAnalysisAdapter,
)
from app.services.backtest.round_analysis_model_registry import (
    ERROR_MODEL_VERSION_MISMATCH,
    RoundAnalysisModelResult,
    model_result_to_block,
)
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig


@patch("app.services.backtest.adapters.sot_v11_round_analysis_adapter.V11RoundAnalysisPreviewService")
def test_v11_incomplete_prediction_error_code(mock_preview_cls):
    mock_preview_cls.return_value.build_fixture_model.return_value = {
        "predicted_home_sot": 4.0,
        "predicted_away_sot": None,
        "predicted_total_sot": None,
        "sample_bucket": "medium_sample",
        "warnings": ["away_prediction_incomplete"],
        "data_quality": {},
        "_meta": {"home_prior_count": 9, "away_prior_count": 9, "player_layer_neutral": False},
    }
    adapter = SotV11RoundAnalysisAdapter()
    result = adapter.predict_fixture(
        MagicMock(),
        fixture=MagicMock(id=1),
        competition_id=1,
        mode="historical_official_xi",
        lines=[8.5],
        cautious_drop_threshold=0.75,
        play_config=PlayAdviceConfig(),
        data_quality={},
        actual_total=10,
    )
    assert result.status == "no_prediction"
    assert result.error_code == ERR_PREDICTION_INCOMPLETE
    assert result.error_code != "INSUFFICIENT_HISTORY"


@patch("app.services.backtest.adapters.sot_v11_round_analysis_adapter.V11RoundAnalysisPreviewService")
def test_v11_zero_prior_error_code(mock_preview_cls):
    mock_preview_cls.return_value.build_fixture_model.return_value = {
        "predicted_total_sot": None,
        "warnings": [],
        "data_quality": {},
        "_meta": {"home_prior_count": 0, "away_prior_count": 5},
    }
    adapter = SotV11RoundAnalysisAdapter()
    result = adapter.predict_fixture(
        MagicMock(),
        fixture=MagicMock(id=1),
        competition_id=1,
        mode="historical_official_xi",
        lines=[8.5],
        cautious_drop_threshold=0.75,
        play_config=PlayAdviceConfig(),
        data_quality={},
        actual_total=None,
    )
    assert result.error_code == ERR_INSUFFICIENT_PRIOR


def test_model_version_mismatch_block():
    result = RoundAnalysisModelResult(
        model_version_requested=BASELINE_SOT_MODEL_VERSION_V11_SOT,
        model_version_used="wrong_model",
        model_engine_name="TestEngine",
        status="ok",
        prediction={"predicted_total_sot": 10.0},
    )
    block = model_result_to_block(result)
    assert block["status"] == "error"
    assert block["error_code"] == ERROR_MODEL_VERSION_MISMATCH
