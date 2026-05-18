"""Parsing fixtures/lineups API blocks."""

from app.services.lineups.lineup_parsing import (
    block_has_official_lineup,
    parse_api_lineup_block,
    parse_lineup_player_lists,
)


SAMPLE_BLOCK = {
    "team": {"id": 489, "name": "AC Milan"},
    "formation": "4-2-3-1",
    "coach": {"name": "Coach Name"},
    "startXI": [
        {"player": {"id": 123, "name": "Player A", "number": 9, "pos": "F", "grid": "4:2"}},
    ],
    "substitutes": [
        {"player": {"id": 456, "name": "Sub B", "number": 12, "pos": "M", "grid": None}},
    ],
}


def test_block_has_official_lineup():
    assert block_has_official_lineup(SAMPLE_BLOCK) is True
    assert block_has_official_lineup({"startXI": []}) is False


def test_parse_api_lineup_block():
    formation, coach, starters, subs = parse_api_lineup_block(SAMPLE_BLOCK)
    assert formation == "4-2-3-1"
    assert coach == "Coach Name"
    assert len(starters) == 1
    assert starters[0].api_player_id == 123
    assert len(subs) == 1
    assert subs[0].is_substitute is True


def test_parse_jsonb_lists():
    starters, subs = parse_lineup_player_lists(SAMPLE_BLOCK["startXI"], SAMPLE_BLOCK["substitutes"])
    assert len(starters) == 1
    assert len(subs) == 1
