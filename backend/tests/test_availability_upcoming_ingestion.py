"""Ingestion availability-upcoming — provider orchestrator."""

from unittest.mock import MagicMock, patch

from app.services.availability.availability_upcoming_ingestion import ingest_serie_a_availability_upcoming


@patch("app.services.availability.availability_upcoming_ingestion.run_availability_upcoming_orchestrator")
def test_upcoming_delegates_to_orchestrator(mock_orchestrator):
    db = MagicMock()
    mock_orchestrator.return_value = {
        "status": "success",
        "season": 2025,
        "fixtures_checked": 1,
        "upcoming_api_fixture_ids": [1378173],
        "providers": {
            "api_football_injuries": {
                "called": True,
                "candidates_total": 1,
                "applicable_saved": 1,
            },
            "api_football_sidelined": {
                "called": True,
                "players_checked": 40,
                "candidates_total": 0,
                "applicable_saved": 0,
            },
        },
        "records_saved": 1,
        "records_updated": 0,
        "provider_future_availability_coverage": "ok",
    }

    summary = ingest_serie_a_availability_upcoming(
        db,
        2025,
        fixture_id=371,
        client=MagicMock(),
    )

    mock_orchestrator.assert_called_once()
    assert summary["records_saved"] == 1
    assert summary["providers"]["api_football_injuries"]["applicable_saved"] == 1
    assert summary["provider_future_availability_coverage"] == "ok"


@patch("app.services.availability.availability_upcoming_ingestion.run_availability_upcoming_orchestrator")
def test_upcoming_empty_coverage(mock_orchestrator):
    mock_orchestrator.return_value = {
        "status": "success",
        "fixtures_checked": 1,
        "providers": {
            "api_football_injuries": {"called": True, "candidates_total": 0, "applicable_saved": 0},
            "api_football_sidelined": {"called": True, "players_checked": 10, "candidates_total": 0},
        },
        "records_saved": 0,
        "provider_future_availability_coverage": "empty",
        "warnings": ["Nessun candidato applicabile."],
    }

    summary = ingest_serie_a_availability_upcoming(MagicMock(), 2025, client=MagicMock())
    assert summary["provider_future_availability_coverage"] == "empty"
    assert len(summary["warnings"]) >= 1
