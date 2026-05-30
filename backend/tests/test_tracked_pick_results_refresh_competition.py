"""Test refresh risultati tracked picks competition-scoped."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.models.competition import Competition
from app.services.tracked_pick_results_refresh_service import TrackedPickResultsRefreshService

client = TestClient(app)

_OK_REFRESH = {
    "status": "ok",
    "competition_id": 2,
    "competition_key": "brasileirao_serie_a_2026",
    "season": 2026,
    "scope": "all",
    "force": False,
    "last_refreshed_at": "2026-05-30T12:00:00+00:00",
    "tracked_checked": 3,
    "updated": 1,
    "picks_checked": 3,
    "picks_updated": 1,
    "api_calls": 2,
    "errors": [],
    "stats_debug": [],
}


@patch("app.routes.admin_competition_ingest.get_settings")
@patch("app.routes.admin_competition_ingest.TrackedPickResultsRefreshService")
def test_refresh_competition_route_calls_service(mock_svc_cls, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_svc_cls.return_value.refresh_results_for_competition.return_value = _OK_REFRESH

    response = client.post(
        "/api/admin/competitions/2/betting-picks/refresh-results",
        json={"scope": "all", "force": False, "model_version": "baseline_v2_1_weighted_components"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["competition_id"] == 2
    assert body["competition_key"] == "brasileirao_serie_a_2026"
    mock_svc_cls.return_value.refresh_results_for_competition.assert_called_once()
    kwargs = mock_svc_cls.return_value.refresh_results_for_competition.call_args.kwargs
    assert kwargs["scope"] == "all"
    assert kwargs["force"] is False
    assert kwargs["model_version"] == "baseline_v2_1_weighted_components"


@patch("app.routes.admin_competition_ingest.get_settings")
@patch("app.routes.admin_competition_ingest.TrackedPickResultsRefreshService")
def test_refresh_competition_empty_picks_returns_200(mock_svc_cls, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_svc_cls.return_value.refresh_results_for_competition.return_value = {
        **_OK_REFRESH,
        "tracked_checked": 0,
        "updated": 0,
        "picks_checked": 0,
        "picks_updated": 0,
        "api_calls": 0,
    }

    response = client.post("/api/admin/competitions/2/betting-picks/refresh-results", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 0
    assert body["tracked_checked"] == 0


@patch("app.routes.admin_competition_ingest.get_settings")
@patch("app.routes.admin_competition_ingest.TrackedPickResultsRefreshService")
def test_refresh_competition_not_found_returns_404(mock_svc_cls, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_svc_cls.return_value.refresh_results_for_competition.side_effect = HTTPException(
        status_code=404,
        detail="Competition 999 non trovata",
    )

    response = client.post("/api/admin/competitions/999/betting-picks/refresh-results", json={})

    assert response.status_code == 404
    assert "999" in response.json()["detail"]


@patch("app.routes.admin_betting_picks.get_settings")
@patch("app.routes.admin_betting_picks.TrackedPickResultsRefreshService")
def test_legacy_serie_a_value_error_returns_422(mock_svc_cls, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_svc_cls.return_value.refresh_results.side_effect = ValueError(
        "Stagione 2026 non trovata per la lega configurata: eseguire prima il bootstrap.",
    )

    response = client.post("/api/admin/betting-picks/serie-a/2026/refresh-results", json={})

    assert response.status_code == 422
    assert "Stagione 2026" in response.json()["detail"]


def test_refresh_results_for_competition_empty_picks():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao_serie_a_2026"
    comp.season = 2026

    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    svc = TrackedPickResultsRefreshService(client=MagicMock())
    with patch("app.services.tracked_pick_results_refresh_service.CompetitionService") as mock_comp_svc:
        mock_comp_svc.return_value.get_by_id_or_raise.return_value = comp
        result = svc.refresh_results_for_competition(db, 2, scope="all", force=False)

    assert result["status"] == "ok"
    assert result["competition_id"] == 2
    assert result["tracked_checked"] == 0
    assert result["updated"] == 0
    assert result["errors"] == []
    db.commit.assert_called_once()
