"""Test runner analisi giornata — isolamento modelli via registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_model_registry import RoundAnalysisModelResult
from app.services.backtest.round_analysis_model_runner import RoundAnalysisModelRunner
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig


@patch("app.services.backtest.round_analysis_model_runner.get_round_analysis_adapter")
def test_run_for_fixture_isolates_model_errors(mock_get_adapter):
    ok_adapter = MagicMock()
    ok_adapter.predict_fixture.return_value = RoundAnalysisModelResult(
        model_version_requested=BASELINE_SOT_MODEL_VERSION_V11_SOT,
        model_version_used=BASELINE_SOT_MODEL_VERSION_V11_SOT,
        model_engine_name="V11RoundAnalysisPreviewService",
        status="ok",
        prediction={"predicted_total_sot": 10.0, "warnings": []},
        picks={"aggressive_line": 8.5},
        label="v1.1",
    )

    fail_adapter = MagicMock()
    fail_adapter.predict_fixture.return_value = RoundAnalysisModelResult(
        model_version_requested=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        model_version_used=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        model_engine_name="SotV21PointInTimePreviewService",
        status="error",
        error_code="V21_ENGINE_ERROR",
        error_message="boom",
        label="v2.1",
    )

    def _factory(key: str):
        if key == BASELINE_SOT_MODEL_VERSION_V11_SOT:
            return ok_adapter
        if key == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS:
            return fail_adapter
        raise ValueError(key)

    mock_get_adapter.side_effect = _factory

    runner = RoundAnalysisModelRunner()
    models_json, _ = runner.run_for_fixture(
        MagicMock(),
        fixture=MagicMock(id=1),
        competition_id=1,
        mode="historical_official_xi",
        models=[BASELINE_SOT_MODEL_VERSION_V11_SOT, BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS],
        lines=[8.5],
        cautious_drop_threshold=0.75,
        play_config=PlayAdviceConfig(),
        data_quality={"lineup": "ok"},
        actual_total=9,
    )

    assert models_json[BASELINE_SOT_MODEL_VERSION_V11_SOT]["status"] == "ok"
    assert models_json[BASELINE_SOT_MODEL_VERSION_V11_SOT]["model_engine_name"] == "V11RoundAnalysisPreviewService"
    assert models_json[BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS]["status"] == "error"
    assert models_json[BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS]["error_code"] == "V21_ENGINE_ERROR"


@patch("app.services.backtest.adapters.sot_v21_round_analysis_adapter.SotV21PointInTimePreviewService")
def test_v21_adapter_none_total_returns_specific_code(mock_preview_cls):
    preview = MagicMock()
    preview.prediction.total_predicted_sot = None
    preview.home_prior_matches_count = 0
    preview.away_prior_matches_count = 0
    preview.warnings = []
    preview.home_trace.macros = []
    preview.away_trace.macros = []
    mock_preview_cls.return_value.build_preview.return_value = preview

    from app.services.backtest.adapters.sot_v21_round_analysis_adapter import SotV21RoundAnalysisAdapter

    adapter = SotV21RoundAnalysisAdapter()
    result = adapter.predict_fixture(
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
    assert result.status == "no_prediction"
    assert result.error_code == "V21_INSUFFICIENT_PRIOR_MATCHES"
