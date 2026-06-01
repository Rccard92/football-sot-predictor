"""Test API simulatore calibrazione."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SIM_PAYLOAD = {
    "report_type": "round_analysis_calibration_simulator_v30",
    "metadata": {"analyzed_fixtures": 330, "analyzed_rounds": 33},
    "baselines": {
        "v1_1_cautious_advised": {"picks": 210, "hit_rate": 66.7},
        "v2_1_cautious_advised": {"picks": 194, "hit_rate": 63.9},
    },
    "ranking": {
        "best_hit_rate": "v2_1_cautious_line_6_5_only",
        "best_hit_rate_sufficient_volume": "v3_safe_6_5_balanced",
        "too_selective": None,
        "weakest": None,
    },
    "strategies": {
        "v3_hybrid_value_selector": {
            "strategy_verdict": "promising",
            "loss_diagnostics": [],
            "by_low_total_risk_v2": {},
            "by_reason_codes": {},
        },
    },
}


@patch("app.routes.backtest_round_analysis.RoundAnalysisCalibrationSimulatorService.get_simulator")
def test_calibration_simulator_200(mock_get):
    mock_get.return_value = SIM_PAYLOAD
    r = client.get(
        "/api/backtest/round-analysis/calibration-simulator",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == "round_analysis_calibration_simulator_v30"
    assert "best_hit_rate_sufficient_volume" in body["ranking"]
    hybrid = body["strategies"]["v3_hybrid_value_selector"]
    assert "strategy_verdict" in hybrid
    assert "loss_diagnostics" in hybrid


@patch("app.routes.backtest_round_analysis.RoundAnalysisCalibrationSimulatorService.get_simulator_report_json")
def test_calibration_simulator_report_json_200(mock_get):
    mock_get.return_value = SIM_PAYLOAD
    r = client.get(
        "/api/backtest/round-analysis/calibration-simulator/report-json",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    assert r.json()["metadata"]["analyzed_fixtures"] == 330
