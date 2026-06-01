"""Test configurazione Round Analysis analyze (PlayAdviceConfig)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import app.services.backtest.round_analysis_service as round_analysis_service_module
from app.services.backtest.round_analysis_service import RoundAnalysisService
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_round_analysis import RoundAnalysisDetailResponse

client = TestClient(app)


def test_play_advice_config_importable_from_service_module():
    assert round_analysis_service_module.PlayAdviceConfig is PlayAdviceConfig


def test_play_advice_config_instantiation():
    cfg = PlayAdviceConfig()
    assert cfg.min_prior_matches_for_play == 10
    assert cfg.min_aggressive_edge_for_play == 0.25


@patch("app.routes.backtest_round_analysis.RoundAnalysisService.analyze")
def test_analyze_route_200(mock_analyze):
    mock_analyze.return_value = RoundAnalysisDetailResponse(
        id=1,
        competition_id=1,
        season_year=2025,
        season_label="2025/2026",
        round_number=8,
        analysis_version=1,
        status="completed",
        mode="historical_official_xi",
        config_json={},
        total_fixtures=10,
        processed_fixtures=10,
        failed_fixtures=0,
        progress_pct=100,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fixtures=[],
    )
    r = client.post(
        "/api/backtest/round-analysis/analyze",
        json={
            "competition_id": 1,
            "season_year": 2025,
            "round_number": 8,
            "force_recalculate": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["analysis"]["round_number"] == 8


@patch("app.routes.backtest_round_analysis.RoundAnalysisService.analyze")
def test_analyze_route_config_error_payload(mock_analyze):
    mock_analyze.side_effect = NameError("PlayAdviceConfig is not defined")
    r = client.post(
        "/api/backtest/round-analysis/analyze",
        json={
            "competition_id": 1,
            "season_year": 2025,
            "round_number": 8,
            "force_recalculate": True,
        },
    )
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert detail["status"] == "error"
    assert detail["error_code"] == "ROUND_ANALYSIS_CONFIG_ERROR"
    assert "error_message" in detail


def test_round_analysis_service_import_smoke():
    svc = RoundAnalysisService()
    assert svc is not None
