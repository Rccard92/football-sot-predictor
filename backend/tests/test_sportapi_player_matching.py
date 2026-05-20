"""Unit test matching giocatori SportAPI ↔ API-Football."""

from app.services.sportapi.sportapi_player_matching_service import (
    _recommendation,
    score_player_match,
)
from app.services.sportapi.sportapi_player_name_normalize import normalize_player_name, player_names_match


def test_normalize_player_name_accents():
    assert normalize_player_name("Moise Kean") == "moise kean"
    assert normalize_player_name("Pongračić") == "pongracic"


def test_player_names_match_apostrophe():
    assert player_names_match("Nicolò Fagioli", "Nicolo Fagioli")


def test_score_exact_name_auto_safe():
    score, breakdown = score_player_match(
        sportapi_name="Moise Kean",
        sportapi_short=None,
        sportapi_position="F",
        sportapi_jersey=9,
        sportapi_raw=None,
        candidate_name="Moise Kean",
        candidate_team_id=100,
        expected_team_id=100,
        season_id=1,
        fixture_season_id=1,
        fixture_league_id=135,
        league_id=135,
        candidate_jersey=9,
    )
    assert score >= 90
    assert breakdown["name"] == 50
    assert _recommendation(score) == "AUTO_SAFE"


def test_score_different_name_no_match():
    score, _ = score_player_match(
        sportapi_name="Unknown Player",
        sportapi_short=None,
        sportapi_position="M",
        sportapi_jersey=None,
        sportapi_raw=None,
        candidate_name="Moise Kean",
        candidate_team_id=100,
        expected_team_id=100,
        season_id=1,
        fixture_season_id=1,
        fixture_league_id=135,
        league_id=135,
    )
    assert score < 75
    assert _recommendation(score) == "NO_MATCH"


def test_recommendation_thresholds():
    assert _recommendation(92) == "AUTO_SAFE"
    assert _recommendation(80) == "REVIEW"
    assert _recommendation(50) == "NO_MATCH"
