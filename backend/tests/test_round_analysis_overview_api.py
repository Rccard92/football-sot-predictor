"""Test API overview aggregato Round Analysis."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.main import app

client = TestClient(app)

OVERVIEW_PAYLOAD = {
    "competition_id": 1,
    "season_year": 2025,
    "season_label": "2025/2026",
    "use_latest_version_per_round": True,
    "rounds_analyzed": 1,
    "fixtures_analyzed": 10,
    "models": {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: {
            "model_key": BASELINE_SOT_MODEL_VERSION_V11_SOT,
            "label": "v1.1",
            "reliability_score": 72.5,
            "sample_status": "provvisorio",
        },
    },
    "rounds": [],
    "ranking": {},
}


@patch("app.routes.backtest_round_analysis.RoundAnalysisOverviewService.get_overview")
def test_get_overview_200(mock_get):
    mock_get.return_value = OVERVIEW_PAYLOAD
    r = client.get(
        "/api/backtest/round-analysis/overview",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["rounds_analyzed"] == 1
    assert BASELINE_SOT_MODEL_VERSION_V11_SOT in body["models"]


@patch("app.routes.backtest_round_analysis.RoundAnalysisOverviewService.get_overview_report_json")
def test_get_overview_report_json_200(mock_get):
    mock_get.return_value = {
        "report_type": "round_analysis_calibration_v3",
        "metadata": {"analyzed_rounds": 1},
        "global_model_summary": {},
        "fixtures": [],
    }
    r = client.get(
        "/api/backtest/round-analysis/overview/report-json",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    assert r.json()["report_type"] == "round_analysis_calibration_v3"


@patch("app.routes.backtest_round_analysis.RoundAnalysisOverviewService.get_overview_report_csv")
def test_get_overview_report_csv_200(mock_get):
    mock_get.return_value = "round,fixture_id\n10,95\n"
    r = client.get(
        "/api/backtest/round-analysis/overview/report-csv",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
