"""Test API analisi giornata (Step I)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_round_analysis import RoundAnalysisDetailResponse, RoundAnalysisListResponse

client = TestClient(app)


def _detail() -> RoundAnalysisDetailResponse:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    return RoundAnalysisDetailResponse(
        id=1,
        competition_id=2,
        season_year=2025,
        season_label="2025/2026",
        round_number=36,
        analysis_version=1,
        status="completed",
        status_label="Completata",
        mode="historical_official_xi",
        config_json={},
        total_fixtures=10,
        processed_fixtures=10,
        failed_fixtures=0,
        failed_models_count=0,
        progress_pct=100.0,
        error_json=None,
        first_recommended_round=3,
        created_at=now,
        completed_at=now,
        fixtures=[],
    )


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_analyze_endpoint(mock_svc_cls):
    mock_svc_cls.return_value.analyze.return_value = _detail()
    res = client.post(
        "/api/backtest/round-analysis/analyze",
        json={
            "competition_id": 2,
            "season_year": 2025,
            "round_number": 36,
            "force_recalculate": False,
        },
    )
    assert res.status_code == 200
    assert res.json()["analysis"]["round_number"] == 36


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_list_endpoint(mock_svc_cls):
    mock_svc_cls.return_value.list_analyses.return_value = RoundAnalysisListResponse(
        items=[],
        total=0,
        limit=20,
        offset=0,
    )
    res = client.get("/api/backtest/round-analysis?competition_id=2&season_year=2025")
    assert res.status_code == 200
    assert res.json()["total"] == 0


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_detail_endpoint(mock_svc_cls):
    mock_svc_cls.return_value.get_detail.return_value = _detail()
    res = client.get("/api/backtest/round-analysis/1")
    assert res.status_code == 200
    assert res.json()["id"] == 1


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_delete_endpoint_smoke(mock_svc_cls):
    from app.schemas.backtest_round_analysis import RoundAnalysisDeleteResponse

    mock_svc_cls.return_value.delete_analysis.return_value = RoundAnalysisDeleteResponse(
        deleted_analysis_id=1,
        deleted_fixture_results=5,
    )
    res = client.delete("/api/backtest/round-analysis/1")
    assert res.status_code == 200
    assert res.json()["deleted_analysis_id"] == 1
