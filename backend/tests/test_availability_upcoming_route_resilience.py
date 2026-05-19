"""Route availability-upcoming: sempre JSON su errori non gestiti."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


@patch("app.routes.admin_ingest.get_settings")
@patch(
    "app.services.availability.availability_upcoming_ingestion.ingest_serie_a_availability_upcoming",
)
def test_route_returns_json_on_unhandled_exception(mock_ingest, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_ingest.side_effect = RuntimeError("boom orchestrator")

    client = TestClient(app)
    res = client.post(
        "/api/admin/ingest/serie-a/2025/availability-upcoming",
        params={"days_ahead": 14, "use_sidelined": "false", "dry_run": "true"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "error"
    assert body["phase"] == "route_handler"
    assert "providers" in body
    assert body["providers"]["api_football_sidelined"]["status"] == "skipped"


@patch("app.routes.admin_ingest.get_settings")
@patch(
    "app.services.availability.availability_upcoming_ingestion.ingest_serie_a_availability_upcoming",
)
def test_route_returns_partial_error_payload(mock_ingest, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_ingest.return_value = {
        "status": "partial_error",
        "phase": "done",
        "message": "Completato con errori",
        "providers": {
            "api_football_injuries": {"called": True, "status": "success"},
            "api_football_sidelined": {"called": True, "status": "error", "error": "timeout"},
        },
        "errors": [],
    }

    client = TestClient(app)
    res = client.post("/api/admin/ingest/serie-a/2025/availability-upcoming")

    assert res.status_code == 200
    assert res.json()["status"] == "partial_error"
