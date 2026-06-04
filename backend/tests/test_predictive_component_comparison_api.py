"""Test API confronto componenti predetto vs actual."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUDIT_KEYS = {
    "predicted_value_pre_match_only",
    "actual_value_post_match_diagnostic_only",
    "actual_contribution_proxy_diagnostic_only",
    "no_weight_mutation",
}


@patch("app.routes.predictive_simulator.PredictiveComponentComparisonService")
def test_list_component_fixtures(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.list_fixture_rows.return_value = {
        "total": 1,
        "limit": 200,
        "offset": 0,
        "items": [
            {
                "key": "avg_sot_for",
                "label": "Media SOT",
                "predicted_value": 4.0,
                "actual_value": 5.0,
                "error_direction": "underestimated",
                "ui_status": "underestimated",
            },
        ],
        "audit": {k: True for k in AUDIT_KEYS},
    }

    r = client.get("/api/predictive-simulator/runs/1/component-actual-comparison/fixtures")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["audit"]["no_weight_mutation"] is True
    assert "decision" not in str(data).lower() or "error_direction" in str(data)


@patch("app.routes.predictive_simulator.PredictiveComponentComparisonService")
def test_report_summary(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.get_report.return_value = {
        "run_id": 1,
        "detail": "summary",
        "round_summary": {"aggregates": []},
        "season_summary": {"strategies": {}},
        "fixtures_in_scope": 5,
        "audit": {k: True for k in AUDIT_KEYS},
    }

    r = client.get(
        "/api/predictive-simulator/runs/1/component-actual-comparison/report?detail=summary",
    )
    assert r.status_code == 200
    assert r.json()["detail"] == "summary"
    assert r.json()["audit"]["predicted_value_pre_match_only"] is True


@patch("app.routes.predictive_simulator.PredictiveComponentComparisonService")
def test_report_run_not_found(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.get_report.return_value = {"error_code": "RUN_NOT_FOUND"}

    r = client.get("/api/predictive-simulator/runs/999/component-actual-comparison/report")
    assert r.status_code == 404


@patch("app.routes.predictive_simulator.PredictiveComponentComparisonService")
def test_round_summary(mock_svc_cls):
    svc = MagicMock()
    mock_svc_cls.return_value = svc
    svc.get_round_summary.return_value = {
        "run_id": 1,
        "round_number": 10,
        "aggregates": [],
        "audit": {k: True for k in AUDIT_KEYS},
    }

    r = client.get("/api/predictive-simulator/runs/1/component-actual-comparison/rounds/10")
    assert r.status_code == 200
    assert r.json()["round_number"] == 10
