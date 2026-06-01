"""Test API debug Round Analysis fixture × modello."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.models import Competition, Fixture
from app.services.backtest.round_analysis_model_registry import RoundAnalysisModelResult

client = TestClient(app)


@patch("app.routes.backtest_debug.get_round_analysis_adapter")
def test_debug_round_analysis_fixture_model(mock_get_adapter):
    fx = MagicMock(spec=Fixture)
    fx.id = 92
    fx.competition_id = 1
    comp = MagicMock(spec=Competition)
    comp.season = 2025

    db = MagicMock()

    def _get(model, pk):
        if model is Fixture and int(pk) == 92:
            return fx
        if model is Competition and int(pk) == 1:
            return comp
        return None

    db.get.side_effect = _get

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db

    adapter = MagicMock()
    adapter.predict_fixture.return_value = RoundAnalysisModelResult(
        model_version_requested="baseline_v1_1_sot",
        model_version_used="baseline_v1_1_sot",
        model_engine_name="V11RoundAnalysisPreviewService",
        status="ok",
        prediction={"predicted_total_sot": 10.0},
        picks={
            "aggressive_line": 8.5,
            "aggressive_advice": "play",
            "cautious_line": 9.5,
            "cautious_advice": "skip",
        },
        trace_summary={
            "fixture_id": 92,
            "formula_inputs": {"context_mode": "production_v11"},
            "formula_outputs": {"home": {"expected_sot": 5.0}},
        },
    )
    mock_get_adapter.return_value = adapter

    try:
        res = client.get(
            "/api/backtest/debug/round-analysis/fixture/92/model/baseline_v1_1_sot",
            params={"competition_id": 1, "season_year": 2025},
        )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["engine"] == "V11RoundAnalysisPreviewService"
    assert body["trace"]["fixture_id"] == 92
    assert body["trace"]["formula_inputs"]["context_mode"] == "production_v11"
    assert body["trace"]["formula_outputs"]["home"]["expected_sot"] == 5.0
    assert body["aggressive"]["line"] == 8.5
    assert body["cautious"]["line"] == 9.5
