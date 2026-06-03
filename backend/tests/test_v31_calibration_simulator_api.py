"""Test API simulatore calibrazione v3.1."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from tests.test_v31_calibration_simulator import _sample_row

client = TestClient(app)


def _fake_payload():
    from app.services.backtest.v31_calibration_simulator_strategies import (
        STRATEGY_LABELS,
        get_strategy_weights_payload,
    )
    from app.services.backtest.v31_calibration_simulator_metrics import (
        regression_metrics,
        summarize_strategy,
    )

    rows = [_sample_row(round_number=r) for r in range(5, 12)]
    from app.services.backtest.v31_calibration_simulator_strategies import simulate_row

    simulated = [simulate_row(r, "v31_equal_weights") for r in rows]
    simulated = [s for s in simulated if s]
    summary = summarize_strategy("v31_equal_weights", simulated, best_mae=0.5)
    return {
        "report_type": "v31_calibration_simulator",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": {
            "competition_id": 1,
            "competition_name": "Serie A",
            "season_year": 2025,
            "fixtures_count": len(rows),
            "strategies_run": 1,
            "recommended_strategy": "v31_equal_weights",
        },
        "strategies": [
            {
                "key": "v31_equal_weights",
                "label": STRATEGY_LABELS["v31_equal_weights"],
                "description": "",
                "weights": get_strategy_weights_payload("v31_equal_weights"),
                **summary,
                "rows_sample": simulated[:3],
            },
        ],
        "best_by": {
            "mae": {"strategy": "v31_equal_weights", "value": summary["regression_metrics"]["mae"]},
            "recommended_strategy": "v31_equal_weights",
        },
        "audit": {
            "anti_leakage": True,
            "forbidden_fields_used": [],
            "legacy_predictions_used_as_features": False,
        },
    }


@patch(
    "app.services.backtest.v31_calibration_simulator_service.V31CalibrationSimulatorService.run_simulator",
    return_value=_fake_payload(),
)
def test_calibration_simulator_api(mock_run):
    r = client.get(
        "/api/backtest/v31/calibration-simulator",
        params={
            "competition_id": 1,
            "season_year": 2025,
            "strategy": "v31_equal_weights",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == "v31_calibration_simulator"
    assert len(body["strategies"]) == 1
    assert body["strategies"][0]["key"] == "v31_equal_weights"
    assert body["audit"]["legacy_predictions_used_as_features"] is False
    mock_run.assert_called_once()
