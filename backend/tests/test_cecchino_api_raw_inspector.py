"""Test API Raw Inspector — Cecchino Fase 51."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.main import app
from app.services.cecchino.cecchino_api_raw_inspector import (
    INSPECTOR_VERSION,
    build_api_raw_inspector,
    build_suggested_xg_mapping,
    find_fields_by_keywords,
)

client = TestClient(app)

FIXTURE_STATISTICS_SAMPLE = [
    {
        "team": {"id": 101, "name": "Nautico Recife"},
        "statistics": [
            {"type": "Shots on Goal", "value": 5},
            {"type": "Expected Goals", "value": "1.42"},
        ],
    },
    {
        "team": {"id": 202, "name": "Fortaleza EC"},
        "statistics": [
            {"type": "Expected Goals", "value": "0.88"},
        ],
    },
]


def test_find_fields_by_keywords_expected_goals_in_statistics():
    matches = find_fields_by_keywords(
        FIXTURE_STATISTICS_SAMPLE,
        endpoint="fixture_statistics",
        origin="api_response",
    )
    types = [str(m.get("type") or "") for m in matches]
    assert any("Expected Goals" in t for t in types)
    assert any(m.get("matched_keyword") == "expected" for m in matches)


def test_find_fields_by_keywords_expected_goals_key():
    payload = {"home": {"expected_goals": 1.25, "shots": 10}}
    matches = find_fields_by_keywords(
        payload,
        endpoint="stats_snapshot",
        origin="db_cache",
    )
    keys = [m.get("key") for m in matches]
    assert "expected_goals" in keys


def test_suggested_xg_mapping_candidate_found():
    home = MagicMock()
    home.id = 1
    home.api_team_id = 101
    home.name = "Nautico Recife"
    away = MagicMock()
    away.id = 2
    away.api_team_id = 202
    away.name = "Fortaleza EC"

    mapping = build_suggested_xg_mapping(
        [],
        home_team=home,
        away_team=away,
        statistics_payloads=[("fixture_statistics", FIXTURE_STATISTICS_SAMPLE)],
    )
    assert mapping["status"] == "candidate_found"
    assert mapping["home_xg_for"]["value"] == pytest.approx(1.42)
    assert mapping["away_xg_for"]["value"] == pytest.approx(0.88)
    assert mapping["home_xg_against"]["value"] == pytest.approx(0.88)
    assert mapping["away_xg_against"]["value"] == pytest.approx(1.42)
    assert mapping["home_xg_for"]["confidence"] == "high"
    assert mapping["home_xg_against"]["confidence"] == "medium"


def test_suggested_xg_mapping_not_found():
    mapping = build_suggested_xg_mapping(
        [],
        home_team=None,
        away_team=None,
        statistics_payloads=[],
    )
    assert mapping["status"] == "not_found"
    assert "no_xg_like_fields_found" in mapping["warnings"]


def _mock_today_row(*, provider_fixture_id: int = 999888, local_fixture_id: int | None = None):
    row = MagicMock()
    row.id = 6957
    row.provider_fixture_id = provider_fixture_id
    row.local_fixture_id = local_fixture_id
    row.competition_id = 10
    row.provider_league_id = 71
    row.provider_season = 2025
    row.home_team_name = "Nautico Recife"
    row.away_team_name = "Fortaleza EC"
    row.league_name = "Copa do Brasil"
    row.raw_fixture_json = {"fixture": {"id": provider_fixture_id}}
    row.stats_snapshot_json = {"input_snapshot": {"expected_goals_hint": "none"}}
    return row


def test_build_inspector_version_and_ids():
    db = MagicMock()
    row = _mock_today_row()
    db.get.return_value = row

    with patch(
        "app.services.cecchino.cecchino_api_raw_inspector._resolve_ids",
        return_value=(
            {
                "today_fixture_id": 6957,
                "fixture_id": None,
                "provider_fixture_id": 999888,
                "league_id": 10,
                "provider_league_id": 71,
                "season": 2025,
                "home_team_id": None,
                "provider_home_team_id": None,
                "away_team_id": None,
                "provider_away_team_id": None,
            },
            None,
            None,
            None,
            None,
        ),
    ):
        result = build_api_raw_inspector(db, 6957, force_refresh=False, include_raw=False)

    assert result["version"] == INSPECTOR_VERSION
    assert result["version"] == "cecchino_api_raw_inspector_v1"
    assert result["ids"]["today_fixture_id"] == 6957
    assert result["ids"]["provider_fixture_id"] == 999888
    assert result["fixture"]["today_fixture_id"] == 6957


def test_force_refresh_false_no_api_calls():
    db = MagicMock()
    row = _mock_today_row()
    db.get.return_value = row
    mock_client = MagicMock()

    with patch(
        "app.services.cecchino.cecchino_api_raw_inspector._resolve_ids",
        return_value=(
            {
                "today_fixture_id": 6957,
                "fixture_id": None,
                "provider_fixture_id": 999888,
                "league_id": 10,
                "provider_league_id": 71,
                "season": 2025,
                "home_team_id": None,
                "provider_home_team_id": None,
                "away_team_id": None,
                "provider_away_team_id": None,
            },
            None,
            None,
            None,
            None,
        ),
    ):
        result = build_api_raw_inspector(
            db,
            6957,
            force_refresh=False,
            include_raw=False,
            client=mock_client,
        )

    mock_client.get_fixture_by_id.assert_not_called()
    mock_client.get_fixture_statistics.assert_not_called()
    assert result["api_usage"]["external_calls_made"] == 0
    assert result["api_usage"]["endpoints_called"] == []


def test_force_refresh_true_calls_provider_methods():
    db = MagicMock()
    row = _mock_today_row()
    row.raw_fixture_json = None
    row.stats_snapshot_json = None
    db.get.return_value = row

    mock_client = MagicMock()
    mock_client.get_fixture_by_id.return_value = {"fixture": {"id": 999888}}
    mock_client.get_fixture_statistics.return_value = FIXTURE_STATISTICS_SAMPLE
    mock_client.get_fixture_events.return_value = []
    mock_client.get_fixture_lineups.return_value = []
    mock_client.get_fixture_players.return_value = []
    mock_client.get.return_value = {"response": {}}

    home = MagicMock()
    home.id = 1
    home.api_team_id = 101
    home.name = "Nautico Recife"
    away = MagicMock()
    away.id = 2
    away.api_team_id = 202
    away.name = "Fortaleza EC"

    with patch(
        "app.services.cecchino.cecchino_api_raw_inspector._resolve_ids",
        return_value=(
            {
                "today_fixture_id": 6957,
                "fixture_id": 500,
                "provider_fixture_id": 999888,
                "league_id": 10,
                "provider_league_id": 71,
                "season": 2025,
                "home_team_id": 1,
                "provider_home_team_id": 101,
                "away_team_id": 2,
                "provider_away_team_id": 202,
            },
            MagicMock(id=500, raw_json=None),
            home,
            away,
            None,
        ),
    ), patch(
        "app.services.cecchino.cecchino_api_raw_inspector._load_fixture_team_stats_payload",
        return_value=([], []),
    ), patch(
        "app.services.cecchino.cecchino_api_raw_inspector.select",
    ) as mock_select:
        mock_select.return_value.where.return_value = MagicMock()
        db.scalars.return_value.all.return_value = []

        result = build_api_raw_inspector(
            db,
            6957,
            force_refresh=True,
            include_raw=False,
            client=mock_client,
        )

    mock_client.get_fixture_by_id.assert_called_once_with(999888)
    mock_client.get_fixture_statistics.assert_called_once_with(999888)
    assert result["api_usage"]["force_refresh"] is True
    assert result["api_usage"]["external_calls_made"] >= 1
    assert "fixture_statistics" in result["api_usage"]["endpoints_called"]


def test_include_raw_false_omits_raw_payloads():
    db = MagicMock()
    row = _mock_today_row()
    db.get.return_value = row

    with patch(
        "app.services.cecchino.cecchino_api_raw_inspector._resolve_ids",
        return_value=(
            {
                "today_fixture_id": 6957,
                "fixture_id": None,
                "provider_fixture_id": 999888,
                "league_id": 10,
                "provider_league_id": 71,
                "season": 2025,
                "home_team_id": None,
                "provider_home_team_id": None,
                "away_team_id": None,
                "provider_away_team_id": None,
            },
            None,
            None,
            None,
            None,
        ),
    ):
        result = build_api_raw_inspector(db, 6957, force_refresh=False, include_raw=False)

    assert "raw_payloads" not in result


def test_include_raw_true_returns_raw_payloads():
    db = MagicMock()
    row = _mock_today_row()
    db.get.return_value = row

    with patch(
        "app.services.cecchino.cecchino_api_raw_inspector._resolve_ids",
        return_value=(
            {
                "today_fixture_id": 6957,
                "fixture_id": None,
                "provider_fixture_id": 999888,
                "league_id": 10,
                "provider_league_id": 71,
                "season": 2025,
                "home_team_id": None,
                "provider_home_team_id": None,
                "away_team_id": None,
                "provider_away_team_id": None,
            },
            None,
            None,
            None,
            None,
        ),
    ):
        result = build_api_raw_inspector(db, 6957, force_refresh=False, include_raw=True)

    assert "raw_payloads" in result
    assert "today_raw_fixture" in result["raw_payloads"]


def test_missing_provider_fixture_id():
    db = MagicMock()
    row = _mock_today_row(provider_fixture_id=0)
    row.provider_fixture_id = 0
    db.get.return_value = row

    with patch(
        "app.services.cecchino.cecchino_api_raw_inspector._resolve_ids",
        return_value=(
            {
                "today_fixture_id": 6957,
                "fixture_id": None,
                "provider_fixture_id": None,
                "league_id": 10,
                "provider_league_id": 71,
                "season": 2025,
                "home_team_id": None,
                "provider_home_team_id": None,
                "away_team_id": None,
                "provider_away_team_id": None,
            },
            None,
            None,
            None,
            None,
        ),
    ):
        mock_client = MagicMock()
        result = build_api_raw_inspector(
            db,
            6957,
            force_refresh=True,
            include_raw=False,
            client=mock_client,
        )

    assert result["status"] == "missing_provider_fixture_id"
    assert "provider_fixture_id_not_found" in result["warnings"]
    mock_client.get_fixture_by_id.assert_not_called()


def test_route_returns_version():
    with patch(
        "app.routes.cecchino_admin.build_api_raw_inspector",
        return_value={
            "version": INSPECTOR_VERSION,
            "status": "available",
            "fixture": {},
            "ids": {},
            "api_usage": {},
            "searched_keywords": [],
            "sources_checked": [],
            "matches_found": [],
            "suggested_xg_mapping": {"status": "not_found"},
            "warnings": [],
        },
    ):
        r = client.get("/api/admin/cecchino/fixtures/6957/api-raw-inspector")
    assert r.status_code == 200
    assert r.json()["version"] == "cecchino_api_raw_inspector_v1"
