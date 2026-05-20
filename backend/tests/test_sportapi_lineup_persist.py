"""Test normalizzazione payload lineups SportAPI."""

from __future__ import annotations

from app.services.sportapi.sportapi_payload import (
    lineups_block,
    missing_from_side,
    players_from_side,
    side_block,
)


def test_lineups_block_nested():
    body = {
        "lineups": {
            "confirmed": False,
            "home": {
                "formation": "4-3-3",
                "players": [{"player": {"id": 1, "name": "A"}, "substitute": False}],
                "missingPlayers": [{"player": {"id": 99, "name": "Injured"}, "reason": "injury"}],
            },
            "away": {
                "formation": "3-5-2",
                "players": [],
                "missingPlayers": [],
            },
        },
    }
    lu = lineups_block(body)
    assert lu.get("confirmed") is False
    home = side_block(lu, "home")
    assert len(players_from_side(home)) == 1
    assert len(missing_from_side(home)) == 1
