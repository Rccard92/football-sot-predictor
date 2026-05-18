"""Raw-check availability debug."""

from unittest.mock import MagicMock

from app.services.availability.availability_raw_check import (
    _build_diagnosis,
    _build_player_search,
    _name_matches,
)


def test_name_matches_rovella():
    assert _name_matches("Nicolò Rovella", "rovella") is True
    assert _name_matches("Other Player", "rovella") is False


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
