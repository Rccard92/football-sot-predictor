"""Test parser cartellini arbitro."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.referee_cards_parser import (
    match_cards_from_statistics_response,
    match_cards_from_team_stats_rows,
)


def test_match_cards_from_statistics_response_sums_teams():
    blocks = [
        {"statistics": [{"type": "Yellow Cards", "value": 3}, {"type": "Red Cards", "value": 0}]},
        {"statistics": [{"type": "Yellow Cards", "value": 2}, {"type": "Red Cards", "value": 1}]},
    ]
    cards = match_cards_from_statistics_response(blocks)
    assert cards.yellow_cards == 5
    assert cards.red_cards == 1


def test_match_cards_from_team_stats_rows():
    home = SimpleNamespace(yellow_cards=4, red_cards=0)
    away = SimpleNamespace(yellow_cards=3, red_cards=1)
    cards = match_cards_from_team_stats_rows(home, away)
    assert cards.yellow_cards == 7
    assert cards.red_cards == 1
