"""Test API recalculate Round Analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_round_analysis import RoundAnalysisDetailResponse

client = TestClient(app)


@patch("app.routes.backtest_round_analysis.RoundAnalysisService.recalculate")
def test_recalculate_200(mock_recalc):
    mock_recalc.return_value = RoundAnalysisDetailResponse(
        id=99,
        competition_id=1,
        season_year=2025,
        season_label="2025/2026",
        round_number=10,
        analysis_version=2,
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
    r = client.post("/api/backtest/round-analysis/42/recalculate")
    assert r.status_code == 200
    assert r.json()["analysis"]["analysis_version"] == 2
    mock_recalc.assert_called_once()
