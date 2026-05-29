"""Test bootstrap competition season validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.competition import Competition
from app.services.competition_ingestion_service import CompetitionIngestionService
from app.services.league_season_api_helpers import (
    SeasonNotAvailableError,
    extract_available_seasons,
    normalize_season_year,
    parse_league_pick,
    season_not_available_payload,
)

client = TestClient(app)


def test_normalize_season_year_accepts_string():
    assert normalize_season_year("2026") == 2026
    assert normalize_season_year(2026) == 2026


def test_extract_available_seasons_from_payload():
    picked = {
        "league": {"id": 71, "name": "Serie A"},
        "country": {"name": "Brazil"},
        "seasons": [{"year": "2024", "current": False}, {"year": 2025, "current": True}],
    }
    assert extract_available_seasons(picked) == [2024, 2025]


def test_parse_league_pick_marks_requested_season():
    picked = {
        "league": {"id": 71, "name": "Serie A"},
        "country": {"name": "Brazil"},
        "seasons": [{"year": 2025, "current": True}],
    }
    info = parse_league_pick(picked=picked, provider_league_id=71, requested_season=2026)
    assert info.requested_season_available is False
    assert info.available_seasons == [2025]


def test_bootstrap_dry_run_raises_season_not_available():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao_serie_a_2026"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.season = 2026
    comp.league_id = None
    comp.season_id = None

    mock_client = MagicMock()
    mock_client.get.return_value = {
        "response": [
            {
                "league": {"id": 71, "name": "Serie A"},
                "country": {"name": "Brazil"},
                "seasons": [{"year": 2025, "current": True}],
            }
        ]
    }

    svc = CompetitionIngestionService(client=mock_client)
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    with pytest.raises(SeasonNotAvailableError) as exc:
        svc.bootstrap(MagicMock(), 2, dry_run=True)

    assert exc.value.payload["code"] == "season_not_available"
    assert exc.value.payload["available_seasons"] == [2025]
    mock_client.get_teams.assert_not_called()


def test_bootstrap_dry_run_success_without_db_writes():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao_serie_a_2026"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.season = 2025
    comp.league_id = None
    comp.season_id = None

    mock_client = MagicMock()
    mock_client.get.return_value = {
        "response": [
            {
                "league": {"id": 71, "name": "Serie A"},
                "country": {"name": "Brazil"},
                "seasons": [{"year": 2025, "current": True}],
            }
        ]
    }
    mock_client.get_teams.return_value = [{"team": {"id": 1}}]
    mock_client.get_fixtures.return_value = []

    svc = CompetitionIngestionService(client=mock_client)
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    db = MagicMock()
    result = svc.bootstrap(db, 2, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["teams_found"] == 1
    assert result["available_seasons"] == [2025]
    db.commit.assert_not_called()


@patch("app.routes.admin_competitions.CompetitionService")
def test_patch_competition_season(mock_svc_cls):
    row = MagicMock()
    row.season = 2026
    row.season_id = 99
    mock_svc_cls.return_value.patch.return_value = row

    response = client.patch(
        "/api/admin/competitions/2",
        json={"season": 2025},
    )
    assert response.status_code == 200
    mock_svc_cls.return_value.patch.assert_called_once()


@patch("app.routes.competition_scoped.CompetitionService")
@patch("app.routes.competition_scoped.build_model_status_for_competition")
def test_competition_model_status_not_initialized(mock_build, mock_svc_cls):
    comp = MagicMock()
    comp.id = 2
    mock_svc_cls.return_value.get_by_id_or_raise.return_value = comp
    mock_build.return_value = (
        {
            "status": "not_initialized",
            "message": "Modello non ancora inizializzato",
            "competition_id": 2,
            "season": 2026,
            "available_model_versions": [],
            "warnings": [],
        },
        200,
    )

    response = client.get("/api/competitions/2/model-status")
    assert response.status_code == 200
    assert response.json()["status"] == "not_initialized"


@patch("app.routes.admin_competition_ingest.CompetitionService")
@patch("app.routes.admin_competition_ingest.CompetitionIngestionService")
@patch("app.routes.admin_competition_ingest.get_settings")
def test_bootstrap_endpoint_returns_422(mock_settings, mock_svc_cls, mock_comp_svc):
    mock_settings.return_value.api_football_key = "test-key"
    mock_comp_svc.return_value.get_by_id_or_raise.return_value = MagicMock()
    payload = season_not_available_payload(
        competition_id=2,
        competition_key="brasileirao_serie_a_2026",
        competition_name="Brasileirão Série A",
        provider_league_id=71,
        requested_season=2026,
        available_seasons=[2024, 2025],
    )
    mock_svc_cls.return_value.bootstrap.side_effect = SeasonNotAvailableError(payload)

    response = client.post(
        "/api/admin/competitions/2/ingest/bootstrap",
        json={"dry_run": True},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "season_not_available"
    assert body["available_seasons"] == [2024, 2025]


def test_season_not_available_payload_shape():
    payload = season_not_available_payload(
        competition_id=2,
        competition_key="brasileirao_serie_a_2026",
        competition_name="Brasileirão Série A",
        provider_league_id=71,
        requested_season=2026,
        available_seasons=[2024, 2025],
        league_name="Serie A",
        country="Brazil",
    )
    assert payload["code"] == "season_not_available"
    assert payload["available_seasons"] == [2024, 2025]
