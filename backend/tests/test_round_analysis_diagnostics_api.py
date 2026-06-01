"""Test API diagnostica Round Analysis."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.main import app

client = TestClient(app)

DIAG_PAYLOAD = {
    "report_type": "round_analysis_diagnostics_v30",
    "metadata": {
        "competition_id": 1,
        "season_year": 2025,
        "season_label": "2025/2026",
        "analyzed_rounds": 32,
        "analyzed_fixtures": 320,
        "generated_at": "2026-01-01T00:00:00+00:00",
    },
    "models": {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: {"overview": {"label": "v1.1"}},
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: {"overview": {"label": "v2.0"}},
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: {"overview": {"label": "v2.1"}},
    },
    "v21_diagnostics": {"macro_buckets": {}, "low_total_risk": {}},
    "critical_matches": [],
}


@patch("app.routes.backtest_round_analysis.RoundAnalysisDiagnosticsService.get_diagnostics")
def test_get_diagnostics_200(mock_get):
    mock_get.return_value = DIAG_PAYLOAD
    r = client.get(
        "/api/backtest/round-analysis/diagnostics",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == "round_analysis_diagnostics_v30"
    assert len(body["models"]) == 3


@patch("app.routes.backtest_round_analysis.RoundAnalysisDiagnosticsService.get_diagnostics_report_json")
def test_get_diagnostics_report_json_200(mock_get):
    mock_get.return_value = DIAG_PAYLOAD
    r = client.get(
        "/api/backtest/round-analysis/diagnostics/report-json",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    assert r.json()["metadata"]["analyzed_fixtures"] == 320
