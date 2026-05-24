"""Test parser cartellini arbitro."""

from __future__ import annotations

from types import SimpleNamespace

import json
from pathlib import Path

from app.services.referee_cards_parser import (
    match_cards_from_events,
    match_cards_from_statistics_response,
    match_cards_from_team_stats_rows,
)

EVENTS_JSON = Path(__file__).resolve().parent / "fixtures" / "api_football" / "sample_fixture_events.json"


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


def test_match_cards_from_events_by_team():
    events = json.loads(EVENTS_JSON.read_text(encoding="utf-8"))
    side = match_cards_from_events(events, home_team_api_id=10, away_team_api_id=20)
    assert side.total_yellow == 2
    assert side.total_red == 1
    assert side.home_yellow == 1
    assert side.away_yellow == 1
    assert side.home_red == 1
