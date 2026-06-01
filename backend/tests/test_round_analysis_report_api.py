"""Test API report JSON Round Analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.core.database import get_db
from app.main import app
from app.models import BacktestRoundAnalysis, BacktestRoundFixtureResult, Competition

client = TestClient(app)


def _model_block_ok(model_key: str, engine: str, total: float = 10.0) -> dict:
    return {
        "label": model_key,
        "model_version_requested": model_key,
        "model_version_used": model_key,
        "model_engine_name": engine,
        "status": "ok",
        "predicted_home_sot": total / 2,
        "predicted_away_sot": total / 2,
        "predicted_total_sot": total,
        "aggressive_line": 8.5,
        "aggressive_advice": "play",
        "aggressive_outcome": "WIN",
        "cautious_line": 9.5,
        "cautious_advice": "no_play",
        "trace_summary": {"leakage_guard": True, "actuals_used_as_input": False},
    }


@patch("app.services.backtest.round_analysis_report_service.RoundAnalysisReportService._load_analysis_context")
def test_round_report_json(mock_load):
    analysis = MagicMock(spec=BacktestRoundAnalysis)
    analysis.id = 1
    analysis.competition_id = 1
    analysis.season_year = 2025
    analysis.round_number = 10
    analysis.analysis_version = 1
    analysis.status = "completed"
    analysis.mode = "historical_official_xi"
    analysis.config_json = {
        "models": [
            BASELINE_SOT_MODEL_VERSION_V11_SOT,
            BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
            BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        ],
        "lines": [8.5, 9.5],
        "cautious_drop_threshold": 0.75,
        "advice_filters": {},
        "season_label": "2025/2026",
    }
    analysis.total_fixtures = 1
    analysis.processed_fixtures = 1
    analysis.failed_fixtures = 0
    analysis.data_quality_summary_json = {"badge": "OK"}
    analysis.model_summary_json = {}
    analysis.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    analysis.completed_at = datetime(2025, 1, 2, tzinfo=timezone.utc)

    row = MagicMock(spec=BacktestRoundFixtureResult)
    row.fixture_id = 92
    row.round_number = 10
    row.home_team_name = "Udinese"
    row.away_team_name = "Atalanta"
    row.actual_home_sot = 5
    row.actual_away_sot = 4
    row.actual_total_sot = 9
    row.status = "ok"
    row.error_message = None
    row.models_json = {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: _model_block_ok(
            BASELINE_SOT_MODEL_VERSION_V11_SOT,
            "V11RoundAnalysisPreviewService",
        ),
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: _model_block_ok(
            BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
            "V20RoundAnalysisPreviewService",
        ),
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: _model_block_ok(
            BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "SotV21PointInTimePreviewService",
        ),
    }
    row.explanation_json = {
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: {
            "leakage_guard": True,
            "actuals_used_as_input": False,
            "home": {"macros": [{"key": "split", "status": "available", "macro_index": 1.0}]},
        },
    }

    comp = MagicMock(spec=Competition)
    comp.name = "Serie A"
    kickoff = datetime(2025, 10, 1, 15, 0, tzinfo=timezone.utc)
    mock_load.return_value = (analysis, [row], "Serie A", {92: kickoff})

    db = MagicMock()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        res = client.get("/api/backtest/round-analysis/1/report-json")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["report_type"] == "round_analysis"
    assert body["analysis"]["competition_name"] == "Serie A"
    assert len(body["fixtures"]) == 1
    fx = body["fixtures"][0]
    assert fx["actuals"]["used_as_input"] is False
    assert len(fx["models"]) == 3
    v11 = fx["models"][BASELINE_SOT_MODEL_VERSION_V11_SOT]
    assert v11["status"] == "ok"
    assert v11["model_version_requested"] == v11["model_version_used"]
    assert v11["trace_summary"]["actuals_used_as_input"] is False


@patch("app.services.backtest.round_analysis_report_service.RoundAnalysisReportService._load_analysis_context")
def test_fixture_report_json(mock_load):
    analysis = MagicMock(spec=BacktestRoundAnalysis)
    analysis.id = 1
    analysis.competition_id = 1
    analysis.season_year = 2025
    analysis.round_number = 10
    analysis.analysis_version = 1
    analysis.config_json = {"models": [BASELINE_SOT_MODEL_VERSION_V11_SOT], "season_label": "2025/2026"}

    row = MagicMock(spec=BacktestRoundFixtureResult)
    row.fixture_id = 92
    row.round_number = 10
    row.home_team_name = "Udinese"
    row.away_team_name = "Atalanta"
    row.actual_home_sot = 5
    row.actual_away_sot = 4
    row.actual_total_sot = 9
    row.status = "ok"
    row.error_message = None
    row.models_json = {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: _model_block_ok(
            BASELINE_SOT_MODEL_VERSION_V11_SOT,
            "V11RoundAnalysisPreviewService",
        ),
    }
    row.explanation_json = {}

    mock_load.return_value = (analysis, [row], "Serie A", {92: None})

    db = MagicMock()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        res = client.get("/api/backtest/round-analysis/1/fixtures/92/report-json")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["report_type"] == "round_analysis_fixture"
    assert body["fixture"]["fixture_id"] == 92
    assert body["fixture"]["models"][BASELINE_SOT_MODEL_VERSION_V11_SOT]["betting"]["aggressive"]["line"] == 8.5
