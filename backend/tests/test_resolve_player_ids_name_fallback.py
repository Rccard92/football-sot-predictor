"""Test fallback mapping nome+team per indisponibili (Step K.5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models import Player
from app.services.backtest.pit_player_rolling_stats import RawPlayerRow, resolve_player_ids


def test_name_team_fallback_unique_match():
    player = MagicMock(spec=Player)
    player.id = 42
    player.api_player_id = 999
    player.name = "Christian Pulisic"
    player.team_id = 1

    db = MagicMock()
    db.scalars.return_value.all.side_effect = [
        [],  # PlayerProviderMapping
        [player],  # Player by team_id
    ]

    row = RawPlayerRow(
        player_name="Christian Pulišić",
        provider_player_id=817957,
        api_player_id=None,
        position="LW",
        is_starter=False,
        is_unavailable=True,
        absence_group="injured",
    )
    pid, internal_id, status, _warnings = resolve_player_ids(db, row, team_id=1)
    assert internal_id == 42
    assert status == "matched_name_fallback"
    assert pid == 817957


def test_name_team_fallback_ambiguous():
    p1 = MagicMock(spec=Player)
    p1.id = 1
    p1.name = "John Smith"
    p2 = MagicMock(spec=Player)
    p2.id = 2
    p2.name = "John Smith"

    db = MagicMock()
    db.scalars.return_value.all.side_effect = [
        [],
        [p1, p2],
    ]

    row = RawPlayerRow(
        player_name="John Smith",
        provider_player_id=100,
        api_player_id=None,
        position="ST",
        is_starter=False,
        is_unavailable=True,
    )
    _pid, internal_id, status, _warnings = resolve_player_ids(db, row, team_id=1)
    assert internal_id is None
    assert status == "ambiguous"
