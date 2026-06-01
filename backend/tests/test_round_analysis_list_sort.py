"""Test ordinamento lista analisi giornata (Step I)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.backtest_round_analysis import RoundAnalysisListResponse
from app.services.backtest.round_analysis_service import _list_order_clauses

client = TestClient(app)


def test_list_order_clauses_round_number_includes_created_at_desc():
    clauses = _list_order_clauses("round_number", "desc")
    assert len(clauses) == 3
    third = str(clauses[2]).upper()
    assert "CREATED_AT" in third
    assert "DESC" in third


def test_list_order_clauses_created_at_primary():
    clauses = _list_order_clauses("created_at", "asc")
    assert len(clauses) == 3
    first = str(clauses[0]).upper()
    assert "CREATED_AT" in first
    assert "ASC" in first
    assert "ROUND_NUMBER" in str(clauses[1]).upper()
    assert "ANALYSIS_VERSION" in str(clauses[2]).upper()


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_list_endpoint_passes_sort_params(mock_svc_cls):
    mock_svc_cls.return_value.list_analyses.return_value = RoundAnalysisListResponse(
        items=[],
        total=0,
        limit=20,
        offset=0,
    )
    res = client.get(
        "/api/backtest/round-analysis",
        params={
            "competition_id": 2,
            "season_year": 2025,
            "sort_by": "round_number",
            "sort_dir": "desc",
        },
    )
    assert res.status_code == 200
    mock_svc_cls.return_value.list_analyses.assert_called_once()
    call_kw = mock_svc_cls.return_value.list_analyses.call_args.kwargs
    assert call_kw["sort_by"] == "round_number"
    assert call_kw["sort_dir"] == "desc"


@patch("app.routes.backtest_round_analysis.RoundAnalysisService")
def test_delete_route_registered(mock_svc_cls):
    mock_svc_cls.return_value.delete_analysis.return_value = MagicMock(
        status="ok",
        deleted_analysis_id=1,
        deleted_fixture_results=0,
    )
    res = client.delete("/api/backtest/round-analysis/1")
    assert res.status_code == 200
