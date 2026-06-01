"""Test DELETE analisi giornata (Step I)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_round_analysis import RoundAnalysisDeleteResponse

client = TestClient(app)


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_delete_not_found(mock_svc_cls):
    from fastapi import HTTPException

    mock_svc_cls.return_value.delete_analysis.side_effect = HTTPException(
        status_code=404,
        detail={"code": "analysis_not_found", "message": "Analisi non trovata."},
    )
    res = client.delete("/api/backtest/round-analysis/99999")
    assert res.status_code == 404


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_delete_success(mock_svc_cls):
    mock_svc_cls.return_value.delete_analysis.return_value = RoundAnalysisDeleteResponse(
        deleted_analysis_id=7,
        deleted_fixture_results=120,
    )
    res = client.delete("/api/backtest/round-analysis/7")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["deleted_analysis_id"] == 7
    assert body["deleted_fixture_results"] == 120
    mock_svc_cls.return_value.delete_analysis.assert_called_once()
