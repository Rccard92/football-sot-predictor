"""Test API laboratorio predittivo persistente."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.services.backtest.v31_predictive_reason_codes import build_reason_codes, derive_outcome_type

client = TestClient(app)


def _fake_run_result():
    from tests.test_v31_calibration_simulator_api import _fake_payload

    sim = _fake_payload()
    pattern = {
        "report_type": "v31_pattern_analysis",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": {
            "competition_id": 1,
            "season_year": 2025,
            "fixtures_count": 7,
            "pattern_verdict": {"main_issue": "models_understate_high_non_extreme"},
            "top3_cluster_summary": {"counts": {}},
            "actual_sot_distribution": {"mean": 9.0, "p75": 10.0},
            "dynamic_bucket_thresholds": {"p25": 7.0, "p75": 10.0, "p90": 11.0, "p95": 12.0},
        },
        "strategies": [],
        "audit": {"pattern_analysis_no_weight_mutation": True},
    }
    return {
        "run_id": 42,
        "summary": {
            "competition_id": 1,
            "season_year": 2025,
            "fixtures_count": 7,
            "strategies_count": 1,
            "recommended_strategy": "v31_equal_weights",
            "main_warning": "models_understate_high_non_extreme",
            "insights_count": 2,
        },
        "simulator": sim,
        "pattern": pattern,
        "insights": [
            {
                "insight_type": "main_warning",
                "severity": "warning",
                "title": "Warning",
                "description": "Test",
                "evidence_json": {},
            },
        ],
        "audit": {
            "anti_leakage": True,
            "actual_post_match_only": True,
            "betting_phase_enabled": False,
        },
        "message": "Analisi salvata nello storico",
    }


def _mock_run_row():
    run = MagicMock()
    run.id = 42
    run.competition_id = 1
    run.season_year = 2025
    run.season_label = "2025/2026"
    run.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run.fixtures_count = 7
    run.strategies_count = 1
    run.recommended_strategy = "v31_equal_weights"
    run.run_type = "full_lab"
    run.model_version = "v3.1"
    run.betting_phase_enabled = False
    run.summary_json = {
        "best_mae_strategy": "v31_equal_weights",
        "main_warning": "test warning",
    }
    run.simulator_payload_json = _fake_run_result()["simulator"]
    run.pattern_payload_json = _fake_run_result()["pattern"]
    run.audit_json = _fake_run_result()["audit"]
    return run


@patch(
    "app.routes.predictive_simulator.PredictiveSimulationRunService.create_and_run",
    return_value=_fake_run_result(),
)
def test_post_predictive_run(mock_create):
    r = client.post(
        "/api/predictive-simulator/run",
        json={"competition_id": 1, "season_year": 2025, "persist": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == 42
    assert "storico" in body["message"].lower()
    mock_create.assert_called_once()


@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.list_runs")
def test_list_predictive_runs(mock_list):
    mock_list.return_value = [
        {
            "run_id": 42,
            "competition_id": 1,
            "season_year": 2025,
            "fixtures_count": 7,
            "strategies_count": 1,
            "recommended_strategy": "v31_equal_weights",
            "best_mae_strategy": "v31_equal_weights",
            "main_warning": "warn",
            "run_type": "full_lab",
            "model_version": "v3.1",
        },
    ]
    r = client.get("/api/predictive-simulator/runs", params={"competition_id": 1})
    assert r.status_code == 200
    assert r.json()[0]["run_id"] == 42


@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.get_run")
def test_get_predictive_run(mock_get):
    mock_get.return_value = {
        "run_id": 42,
        "competition_id": 1,
        "season_year": 2025,
        "summary": {},
        "simulator": {},
        "pattern": {},
        "insights": [],
        "audit": {"betting_phase_enabled": False},
        "betting_phase_enabled": False,
    }
    r = client.get("/api/predictive-simulator/runs/42")
    assert r.status_code == 200
    assert r.json()["run_id"] == 42


@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.get_run")
@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.get_fixtures")
def test_get_fixtures_filtered(mock_fixtures, mock_get):
    mock_get.return_value = {"run_id": 42}
    mock_fixtures.return_value = {
        "total": 1,
        "limit": 100,
        "offset": 0,
        "items": [
            {
                "fixture_id": 1,
                "strategy_key": "v31_equal_weights",
                "outcome_type": "high_missed",
                "reason_codes": [{"code": "HIGH_TOTAL_MISSED", "label_it": "High"}],
            },
        ],
    }
    r = client.get(
        "/api/predictive-simulator/runs/42/fixtures",
        params={"outcome_type": "high_missed", "strategy_key": "v31_equal_weights"},
    )
    assert r.status_code == 200
    assert r.json()["items"][0]["outcome_type"] == "high_missed"


@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.get_run")
@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.upsert_note")
def test_post_fixture_note(mock_note, mock_get):
    mock_get.return_value = {"run_id": 42}
    mock_note.return_value = {
        "id": 1,
        "run_id": 42,
        "fixture_id": 10,
        "strategy_key": "v31_equal_weights",
        "note": "test nota",
        "tag": None,
    }
    r = client.post(
        "/api/predictive-simulator/runs/42/fixtures/10/notes",
        json={"strategy_key": "v31_equal_weights", "note": "test nota"},
    )
    assert r.status_code == 200
    assert r.json()["note"] == "test nota"


@patch("app.routes.predictive_simulator.openai_configured", return_value=False)
@patch("app.routes.predictive_simulator.PredictiveSimulationRunService.get_run")
def test_ai_insights_not_configured(mock_get, _mock_cfg):
    mock_get.return_value = {"run_id": 42}
    r = client.post("/api/predictive-simulator/runs/42/ai-insights")
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "OPENAI_NOT_CONFIGURED"


def test_reason_codes_on_extreme_row():
    row = {
        "predicted_total_sot": 8.0,
        "actual_total_sot": 14.0,
        "error": -6.0,
        "abs_error": 6.0,
        "predicted_bucket": "normal_total",
        "actual_bucket": "high_total",
        "actual_bucket_dynamic": "extreme_total",
        "win_quality": "EXTREME_WIN_OUTLIER",
        "trace": {"boost_applied": 0.1, "high_total_signal": 60},
    }
    codes = build_reason_codes(row)
    assert len(codes) > 0
    outcome = derive_outcome_type(row, codes)
    assert outcome in ("extreme_win_outlier", "high_missed", "extreme_win_outlier")


def test_config_endpoint():
    r = client.get("/api/predictive-simulator/config")
    assert r.status_code == 200
    assert "openai_configured" in r.json()


def test_run_payload_no_betting_fields():
    payload = _fake_run_result()
    assert "decision" not in str(payload)
    assert payload["audit"].get("betting_phase_enabled") is False
