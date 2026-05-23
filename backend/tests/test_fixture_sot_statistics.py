"""Test estrazione SOT da payload statistics API-Football."""

from __future__ import annotations

from app.services.fixture_sot_statistics import (
    extract_sot_from_statistics_response,
    parse_sot_stat_value,
)


def _block(team_id: int, team_name: str, sot_value: str | int | float, label: str = "Shots on Goal") -> dict:
    return {
        "team": {"id": team_id, "name": team_name},
        "statistics": [{"type": label, "value": sot_value}],
    }


def test_parse_sot_string_and_float():
    assert parse_sot_stat_value("4") == 4.0
    assert parse_sot_stat_value("4.0") == 4.0
    assert parse_sot_stat_value(5) == 5.0
    assert parse_sot_stat_value("-") is None
    assert parse_sot_stat_value("55%") is None


def test_extract_sot_by_api_team_id():
    blocks = [_block(100, "Home FC", "4"), _block(200, "Away FC", "2")]
    out = extract_sot_from_statistics_response(
        blocks,
        home_team_id=1,
        away_team_id=2,
        home_api_team_id=100,
        away_api_team_id=200,
    )
    assert out["sot_available"] is True
    assert out["home_sot"] == 4.0
    assert out["away_sot"] == 2.0
    assert out["total_sot"] == 6.0


def test_extract_sot_reversed_blocks_api_id():
    blocks = [_block(200, "Away FC", 1), _block(100, "Home FC", 3)]
    out = extract_sot_from_statistics_response(
        blocks,
        home_team_id=10,
        away_team_id=20,
        home_api_team_id=100,
        away_api_team_id=200,
    )
    assert out["sot_available"] is True
    assert out["home_sot"] == 3.0
    assert out["away_sot"] == 1.0


def test_extract_sot_by_team_name_without_api_id():
    blocks = [_block(999, "Bologna", 3), _block(888, "Inter", 2)]
    out = extract_sot_from_statistics_response(
        blocks,
        home_team_id=10,
        away_team_id=20,
        home_api_team_id=None,
        away_api_team_id=None,
        home_team_name="Bologna",
        away_team_name="Inter",
    )
    assert out["sot_available"] is True
    assert out["home_sot"] == 3.0
    assert out["away_sot"] == 2.0
    assert out["debug"]["match_method"] == "team_name"


def test_extract_sot_shot_on_target_alias():
    blocks = [_block(100, "Home", 2, label="Shot on Target")]
    blocks.append(_block(200, "Away", 1, label="Shots on Target"))
    out = extract_sot_from_statistics_response(
        blocks,
        home_team_id=1,
        away_team_id=2,
        home_api_team_id=100,
        away_api_team_id=200,
    )
    assert out["total_sot"] == 3.0


def test_extract_sot_tiri_nello_specchio():
    blocks = [_block(100, "Casa", 4, label="Tiri nello specchio")]
    blocks.append(_block(200, "Trasferta", 2, label="Tiri in porta"))
    out = extract_sot_from_statistics_response(
        blocks,
        home_team_id=1,
        away_team_id=2,
        home_api_team_id=100,
        away_api_team_id=200,
    )
    assert out["total_sot"] == 6.0


def test_extract_sot_empty_blocks():
    out = extract_sot_from_statistics_response(
        [],
        home_team_id=1,
        away_team_id=2,
        home_api_team_id=100,
        away_api_team_id=200,
    )
    assert out["sot_available"] is False
    assert out["debug"]["statistics_found"] is False
    assert out["debug"]["extraction_error"] == "empty_response"
