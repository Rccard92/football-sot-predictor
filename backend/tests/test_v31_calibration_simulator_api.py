"""Test API simulatore predittivo v3.1."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from tests.test_v31_calibration_simulator import _sample_row

client = TestClient(app)


def _fake_payload():
    from app.services.backtest.v31_calibration_simulator_metrics import (
        compute_best_by,
        summarize_strategy,
    )
    from app.services.backtest.v31_calibration_simulator_strategies import (
        STRATEGY_LABELS,
        get_strategy_weights_payload,
        predict_rows_for_strategy,
    )

    rows = [_sample_row(round_number=r) for r in range(5, 12)]
    simulated = predict_rows_for_strategy(rows, "v31_equal_weights")
    summary = summarize_strategy("v31_equal_weights", simulated)
    blocks = [
        {
            "key": "v31_equal_weights",
            "label": STRATEGY_LABELS["v31_equal_weights"],
            "description": "",
            "weights": get_strategy_weights_payload("v31_equal_weights"),
            **summary,
            "rows_sample": simulated[:3],
        },
    ]
    best = compute_best_by(blocks, fixtures_total=len(rows))
    return {
        "report_type": "v31_predictive_simulator",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": {
            "competition_id": 1,
            "competition_name": "Serie A",
            "season_year": 2025,
            "fixtures_count": len(rows),
            "strategies_run": 1,
            "recommended_strategy": best.get("recommended_strategy"),
            "phase": "predictive_numeric",
            "betting_phase_enabled": False,
        },
        "strategies": blocks,
        "best_by": best,
        "audit": {
            "anti_leakage": True,
            "forbidden_fields_used": [],
            "legacy_predictions_used_as_features": False,
            "target_used_as_input": False,
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
    assert body["report_type"] == "v31_predictive_simulator"
    assert len(body["strategies"]) == 1
    ed = body["strategies"][0].get("error_distribution") or {}
    worst = (ed.get("worst_overestimations") or []) + (ed.get("worst_underestimations") or [])
    for w in worst:
        assert w.get("probable_reason")
    assert body["strategies"][0]["key"] == "v31_equal_weights"
    assert "betting_metrics" not in body["strategies"][0]
    assert body["audit"]["legacy_predictions_used_as_features"] is False
    mock_run.assert_called_once()


@patch(
    "app.services.backtest.v31_calibration_simulator_service.V31CalibrationSimulatorService.run_simulator",
    return_value=_fake_payload(),
)
def test_calibration_simulator_report_json(mock_run):
    r = client.get(
        "/api/backtest/v31/calibration-simulator/report-json",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    mock_run.assert_called_once()
    call_kw = mock_run.call_args.kwargs
    assert call_kw.get("include_rows") is True
