"""Test GET /api/backtest/debug/health."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.backtest_health_service import BacktestHealthService

client = TestClient(app)

_HEALTH_PAYLOAD = {
    "status": "ok",
    "tables": {
        "backtest_runs": True,
        "backtest_predictions": True,
        "backtest_picks": True,
        "backtest_run_metrics": True,
    },
    "runs_count": 3,
    "predictions_count": 0,
    "picks_count": 0,
    "metrics_count": 0,
    "markets": [{"market_key": "shots_on_target", "status": "active"}],
    "algorithms": [
        {
            "market_key": "shots_on_target",
            "algorithm_version": "baseline_v2_1_weighted_components",
            "status": "production",
        },
    ],
    "active_markets": ["shots_on_target"],
    "planned_markets": ["corners"],
    "active_algorithms": ["baseline_v2_0_lineup_impact", "baseline_v2_1_weighted_components"],
}


@patch("app.routes.backtest_debug.BacktestHealthService")
def test_backtest_debug_health_route(mock_svc_cls):
    mock_svc_cls.return_value.get_health.return_value = _HEALTH_PAYLOAD

    response = client.get("/api/backtest/debug/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["runs_count"] == 3
    assert "shots_on_target" in body["active_markets"]


def test_backtest_health_service_registry():
    db = MagicMock()
    db.get_bind.return_value = MagicMock()
    with patch("app.services.backtest_health_service.get_existing_table_names") as mock_tables:
        mock_tables.return_value = {
            "backtest_runs",
            "backtest_predictions",
            "backtest_picks",
            "backtest_run_metrics",
        }
        db.scalar.side_effect = [2, 0, 0, 0]
        payload = BacktestHealthService().get_health(db)

    assert payload["status"] == "ok"
    assert payload["runs_count"] == 2
    assert any(m["market_key"] == "shots_on_target" for m in payload["markets"])
    assert "baseline_v2_1_weighted_components" in payload["active_algorithms"]
