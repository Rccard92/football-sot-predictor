"""Test discovery competition API-Sports (senza chiamate reali)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.competition_discover_helpers import (
    NO_MATCH_MESSAGE,
    build_leagues_query_params,
    filter_discover_candidates,
    parse_league_response_items,
)
from app.services.competition_service import CompetitionService

client = TestClient(app)


def test_build_leagues_query_params_country_without_search():
    params = build_leagues_query_params("Brazil", "Serie A", 2026)
    assert params == {"season": 2026, "country": "Brazil"}
    assert "search" not in params


def test_build_leagues_query_params_search_without_country():
    params = build_leagues_query_params("", "Serie A", 2026)
    assert params == {"season": 2026, "search": "Serie A"}
    assert "country" not in params


def test_build_leagues_query_params_requires_country_or_name():
    with pytest.raises(Exception) as exc:
        build_leagues_query_params("", "", 2026)
    assert "Paese o Nome lega" in str(exc.value)


def test_parse_league_response_items_extracts_season_current():
    items = [
        {
            "league": {"id": 71, "name": "Serie A", "logo": "https://example/logo.png"},
            "country": {"name": "Brazil"},
            "seasons": [{"year": 2026, "current": True}],
        }
    ]
    parsed = parse_league_response_items(items, 2026)
    assert len(parsed) == 1
    assert parsed[0]["provider_league_id"] == 71
    assert parsed[0]["season_current"] is True
    assert parsed[0]["available_seasons"] == [2026]
    assert parsed[0]["requested_season_available"] is True


def test_parse_league_response_items_keeps_candidate_without_requested_season():
    items = [
        {
            "league": {"id": 71, "name": "Serie A", "logo": "https://example/logo.png"},
            "country": {"name": "Brazil"},
            "seasons": [{"year": 2025, "current": True}],
        }
    ]
    parsed = parse_league_response_items(items, 2026)
    assert len(parsed) == 1
    assert parsed[0]["requested_season_available"] is False
    assert parsed[0]["available_seasons"] == [2025]


def test_filter_discover_candidates_serie_a_aliases():
    candidates = [
        {"name": "Serie A", "country": "Brazil", "provider_league_id": 71},
        {"name": "Serie B", "country": "Brazil", "provider_league_id": 72},
    ]
    primary, other = filter_discover_candidates(
        candidates,
        country="Brazil",
        name_query="Serie A",
    )
    assert len(primary) == 1
    assert primary[0]["provider_league_id"] == 71
    assert other == []


def test_filter_discover_candidates_brasileirao_alias():
    candidates = [
        {"name": "Brasileiro Serie A", "country": "Brazil", "provider_league_id": 71},
    ]
    primary, other = filter_discover_candidates(
        candidates,
        country="Brazil",
        name_query="Serie A",
    )
    assert len(primary) == 1
    assert other == []


def test_filter_discover_candidates_empty_name_returns_all_country():
    candidates = [
        {"name": "Serie A", "country": "Brazil", "provider_league_id": 71},
        {"name": "Serie B", "country": "Brazil", "provider_league_id": 72},
    ]
    primary, other = filter_discover_candidates(
        candidates,
        country="Brazil",
        name_query="",
    )
    assert len(primary) == 2
    assert other == []


def test_filter_discover_candidates_no_match_returns_country_fallback():
    candidates = [
        {"name": "Serie A", "country": "Brazil", "provider_league_id": 71},
        {"name": "Serie B", "country": "Brazil", "provider_league_id": 72},
    ]
    primary, other = filter_discover_candidates(
        candidates,
        country="Brazil",
        name_query="Copa do Brasil",
    )
    assert primary == []
    assert len(other) == 2


def test_discover_service_uses_country_season_only():
    mock_client = MagicMock()
    mock_client.get.return_value = {
        "response": [
            {
                "league": {"id": 71, "name": "Serie A", "logo": None},
                "country": {"name": "Brazil"},
                "seasons": [{"year": 2026, "current": True}],
            }
        ]
    }
    svc = CompetitionService(client=mock_client)
    result = svc.discover(MagicMock(), country="Brazil", name_query="Serie A", season=2026)

    mock_client.get.assert_called_once_with("leagues", {"season": 2026, "country": "Brazil"})
    assert result["candidates"][0]["provider_league_id"] == 71
    assert result["other_candidates"] == []
    assert result["api_query"] == "season=2026&country=Brazil"


def test_discover_service_no_match_populates_other_candidates():
    mock_client = MagicMock()
    mock_client.get.return_value = {
        "response": [
            {
                "league": {"id": 72, "name": "Serie B", "logo": None},
                "country": {"name": "Brazil"},
                "seasons": [{"year": 2026, "current": False}],
            }
        ]
    }
    svc = CompetitionService(client=mock_client)
    result = svc.discover(MagicMock(), country="Brazil", name_query="Serie A", season=2026)

    assert result["candidates"] == []
    assert len(result["other_candidates"]) == 1
    assert result["message"] == NO_MATCH_MESSAGE


@patch("app.routes.admin_competitions.get_settings")
@patch("app.routes.admin_competitions.CompetitionService")
def test_discover_endpoint_response_shape(mock_svc_cls, mock_settings):
    mock_settings.return_value.api_football_key = "test-key"
    mock_svc_cls.return_value.discover.return_value = {
        "candidates": [
            {
                "provider_league_id": 71,
                "name": "Serie A",
                "country": "Brazil",
                "season": 2026,
                "logo": None,
                "season_current": True,
                "raw_payload": {"league": {"id": 71}},
            }
        ],
        "other_candidates": [],
        "ambiguous": False,
        "message": None,
        "api_query": "season=2026&country=Brazil",
    }

    response = client.post(
        "/api/admin/competitions/discover",
        json={"country": "Brazil", "name_query": "Serie A", "season": 2026},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["provider_league_id"] == 71
    assert body["other_candidates"] == []
    assert body["api_query"] == "season=2026&country=Brazil"
    mock_svc_cls.return_value.discover.assert_called_once()
