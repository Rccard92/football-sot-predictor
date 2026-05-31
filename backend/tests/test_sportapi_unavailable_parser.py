"""Test parser unavailable SportAPI (Step K.2)."""

from __future__ import annotations

from app.services.sportapi.sportapi_unavailable_parser import (
    collect_detected_paths,
    parse_sportapi_unavailable_from_lineup_payload,
)


def test_parse_missing_players_primary_path():
    payload = {
        "lineups": {
            "home": {
                "missingPlayers": [
                    {"player": {"id": 10, "name": "Injured A"}, "reason": "injury"},
                ],
            },
            "away": {
                "injured": [{"player": {"id": 20, "name": "Injured B"}, "type": "muscle"}],
            },
        },
    }
    rows = parse_sportapi_unavailable_from_lineup_payload(
        payload,
        internal_fixture_id=146,
        provider_event_id=999,
        home_team_id=1,
        away_team_id=2,
        provider_home_team_id=101,
        provider_away_team_id=102,
    )
    assert len(rows) == 2
    assert all(r.source_fixture_id == 146 for r in rows)
    assert all(r.fixture_id == 146 for r in rows)
    home_rows = [r for r in rows if r.team_side == "home"]
    away_rows = [r for r in rows if r.team_side == "away"]
    assert len(home_rows) == 1
    assert len(away_rows) == 1
    assert home_rows[0].status in ("injured", "unavailable", "unknown")
    paths = collect_detected_paths(rows)
    assert any("missingPlayers" in p for p in paths)


def test_parse_dedup_same_player():
    payload = {
        "lineups": {
            "home": {
                "missingPlayers": [
                    {"player": {"id": 10, "name": "Dup"}, "reason": "injury"},
                ],
                "injured": [
                    {"player": {"id": 10, "name": "Dup"}, "type": "injury"},
                ],
            },
            "away": {},
        },
    }
    rows = parse_sportapi_unavailable_from_lineup_payload(
        payload,
        internal_fixture_id=359,
        provider_event_id=888,
        home_team_id=1,
        away_team_id=2,
        provider_home_team_id=None,
        provider_away_team_id=None,
    )
    assert len(rows) == 1
    assert rows[0].source_fixture_id == 359
