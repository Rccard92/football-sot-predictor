"""Raw-check availability debug."""

import importlib
from unittest.mock import MagicMock

from app.services.availability.availability_raw_check import (
    _build_diagnosis,
    _build_player_search,
    _name_matches,
    _serialize_profile_match,
)


def test_name_matches_rovella():
    assert _name_matches("Nicolò Rovella", "rovella") is True
    assert _name_matches("Other Player", "rovella") is False


def test_module_does_not_reference_player_season_profile_player_name():
    mod = importlib.import_module("app.services.availability.availability_raw_check")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "PlayerSeasonProfile.player_name" not in src
    assert "prof.player_name" not in src


def test_serialize_profile_match_with_registry():
    prof = MagicMock()
    prof.api_player_id = 42
    prof.team_id = 1
    prof.api_team_id = 487
    prof.shooting_impact_score = None
    prof.shots_on_per90 = None
    prof.team_sot_share = None
    prof.registry = MagicMock()
    prof.registry.name = "Nicolò Rovella"

    entry, warn = _serialize_profile_match(prof)
    assert entry["player_name"] == "Nicolò Rovella"
    assert entry["api_player_id"] == 42
    assert warn is None


def test_serialize_profile_match_without_registry():
    prof = MagicMock()
    prof.api_player_id = 99
    prof.team_id = 1
    prof.api_team_id = 487
    prof.shooting_impact_score = None
    prof.shots_on_per90 = None
    prof.team_sot_share = None
    prof.registry = None

    entry, warn = _serialize_profile_match(prof)
    assert entry["player_name"] is None
    assert warn is not None
    assert "senza player_registry" in warn


def test_build_diagnosis_coverage_false():
    diag = _build_diagnosis(
        coverage={"injuries": False},
        api_checks={
            "by_fixture": {"results": 0},
            "home_team": {"results": 0},
            "away_team": {"results": 0},
            "league_season": {"results": 0},
        },
        db_fixture=[],
        db_teams=[],
        player_search=None,
    )
    assert any("coverage.injuries=false" in d for d in diag)


def test_build_diagnosis_rovella_not_in_api():
    diag = _build_diagnosis(
        coverage={"injuries": True},
        api_checks={
            "by_fixture": {"results": 0},
            "home_team": {"results": 0},
            "away_team": {"results": 0},
            "league_season": {"results": 0},
        },
        db_fixture=[],
        db_teams=[],
        player_search={
            "query": "Rovella",
            "found_in_api_by_fixture": False,
            "found_in_api_home_team": False,
            "found_in_api_away_team": False,
            "found_in_api_league_season": False,
            "found_in_db_availability": False,
        },
    )
    assert any("Rovella non trovato" in d for d in diag)


def test_build_player_search_found_in_api_home():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    ps = _build_player_search(
        db,
        query="Rovella",
        api_checks={
            "by_fixture": {"players": []},
            "home_team": {
                "players": [{"name": "Nicolò Rovella", "api_player_id": 1}],
            },
            "away_team": {"players": []},
            "league_season": {"players": []},
        },
        season_year=2025,
        league_id=135,
        api_home_team_id=487,
        api_away_team_id=1001,
        db_fixture=[],
        db_teams=[],
    )
    assert ps["found_in_api_home_team"] is True


def test_build_player_search_profiles_via_registry_join():
    db = MagicMock()
    prof = MagicMock()
    prof.api_player_id = 100
    prof.team_id = 1
    prof.api_team_id = 487
    prof.shooting_impact_score = None
    prof.shots_on_per90 = None
    prof.team_sot_share = None
    prof.registry = MagicMock()
    prof.registry.name = "Nicolò Rovella"

    registry_call = MagicMock()
    registry_call.all.return_value = []
    profile_call = MagicMock()
    profile_call.all.return_value = [prof]

    db.scalars.side_effect = [registry_call, profile_call]

    ps = _build_player_search(
        db,
        query="Rovella",
        api_checks={
            "by_fixture": {"players": []},
            "home_team": {"players": []},
            "away_team": {"players": []},
            "league_season": {"players": []},
        },
        season_year=2025,
        league_id=135,
        api_home_team_id=487,
        api_away_team_id=1001,
        db_fixture=[],
        db_teams=[],
    )
    assert ps["found_in_player_season_profiles"] is True
    matches = [m for m in ps["possible_matches"] if m.get("source") == "player_season_profiles"]
    assert len(matches) == 1
    assert matches[0]["player_name"] == "Nicolò Rovella"
