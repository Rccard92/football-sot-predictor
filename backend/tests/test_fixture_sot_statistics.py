"""Test estrazione SOT da payload statistics API-Football."""

from __future__ import annotations

from app.services.fixture_sot_statistics import (
    extract_sot_from_statistics_response,
    parse_sot_stat_value,
)


def _block(team_id: int, sot_value: str | int | float, label: str = "Shots on Goal") -> dict:
    return {
        "team": {"id": team_id, "name": "Team"},
        "statistics": [{"type": label, "value": sot_value}],
    }


def test_parse_sot_string_and_float():
    assert parse_sot_stat_value("4") == 4.0
    assert parse_sot_stat_value("4.0") == 4.0
    assert parse_sot_stat_value(5) == 5.0


def test_extract_sot_by_api_team_id():
    blocks = [_block(100, "4"), _block(200, "2")]
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


def test_extract_sot_order_fallback_two_blocks():
    blocks = [_block(999, "3"), _block(888, "1")]
    out = extract_sot_from_statistics_response(
        blocks,
        home_team_id=10,
        away_team_id=20,
        home_api_team_id=None,
        away_api_team_id=None,
    )
    assert out["sot_available"] is True
    assert out["home_sot"] == 3.0
    assert out["away_sot"] == 1.0
    assert out["debug"]["match_method"] == "order_fallback"


def test_extract_sot_empty_blocks():
    out = extract_sot_from_statistics_response(
        [],
        home_team_id=1,
        away_team_id=2,
        home_api_team_id=100,
        away_api_team_id=200,
    )
    assert out["sot_available"] is False
    assert out["total_sot"] is None
    assert "vuote" in (out["sot_unavailable_reason"] or "").lower()
