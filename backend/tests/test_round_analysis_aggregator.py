"""Test aggregazione summary modelli Round Analysis."""

from __future__ import annotations

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.backtest.round_analysis_aggregator import RoundAnalysisAggregator


def test_summarize_model_warnings_display():
    fixture_results = [
        {
            "status": "ok",
            "actual_total_sot": 10,
            "models_json": {
                BASELINE_SOT_MODEL_VERSION_V11_SOT: {
                    "status": "ok",
                    "predicted_total_sot": 9.0,
                    "aggressive_outcome": "WIN",
                    "model_engine_name": "V11RoundAnalysisPreviewService",
                },
            },
        },
        {
            "status": "ok",
            "actual_total_sot": 8,
            "models_json": {
                BASELINE_SOT_MODEL_VERSION_V11_SOT: {
                    "status": "no_prediction",
                    "error_code": "V11_PREDICTION_INCOMPLETE",
                },
            },
        },
    ]
    summary = RoundAnalysisAggregator().build_model_summary(
        models=[BASELINE_SOT_MODEL_VERSION_V11_SOT],
        fixture_results=fixture_results,
    )[BASELINE_SOT_MODEL_VERSION_V11_SOT]
    assert summary["display"] == "WARNINGS"
    assert summary["fixtures_ok"] == 1
    assert summary["fixtures_nd"] == 1
    assert summary["prevalent_error_code"] == "V11_PREDICTION_INCOMPLETE"


def test_summarize_model_error_display():
    fixture_results = [
        {
            "status": "ok",
            "models_json": {
                BASELINE_SOT_MODEL_VERSION_V11_SOT: {
                    "status": "error",
                    "error_code": "MODEL_ERROR",
                },
            },
        },
    ]
    summary = RoundAnalysisAggregator().build_model_summary(
        models=[BASELINE_SOT_MODEL_VERSION_V11_SOT],
        fixture_results=fixture_results,
    )[BASELINE_SOT_MODEL_VERSION_V11_SOT]
    assert summary["display"] == "ERROR"
    assert summary["fixtures_error"] == 1
