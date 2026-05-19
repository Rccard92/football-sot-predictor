"""Parsing injuries API → record availability."""

from app.services.availability.availability_parsing import parse_injuries_item


SAMPLE_INJURY = {
    "player": {"id": 123, "name": "Player A"},
    "team": {"id": 489, "name": "AC Milan"},
    "fixture": {"id": 999, "date": "2025-05-20T18:45:00+00:00"},
    "type": "Missing Fixture",
    "reason": "Knee Injury",
}


def test_parse_injuries_item_maps_status():
    rec = parse_injuries_item(SAMPLE_INJURY)
    assert rec is not None
    assert rec.availability_status == "out"
    assert rec.availability_type == "injury"
    assert rec.api_player_id == 123
    assert rec.api_fixture_id == 999
    assert rec.source == "api_football_injuries"


def test_parse_injuries_suspension_yellow_cards():
    item = {**SAMPLE_INJURY, "type": "Yellow Cards", "reason": "Accumulation"}
    rec = parse_injuries_item(item)
    assert rec is not None
    assert rec.availability_status == "suspended"
    assert rec.availability_type == "suspension"


def test_parse_injuries_player_type_squalifica():
    item = {
        "player": {"id": 1, "name": "Nicolò Rovella", "type": "Yellow Cards", "reason": "Squalifica"},
        "team": {"id": 487, "name": "Lazio"},
        "fixture": {"id": 100},
    }
    rec = parse_injuries_item(item)
    assert rec is not None
    assert rec.availability_status == "suspended"
    assert rec.availability_type == "suspension"
    assert rec.reason == "Squalifica"


def test_parse_injuries_hamstring_thigh():
    item = {**SAMPLE_INJURY, "type": "Missing Fixture", "reason": "Hamstring Injury"}
    rec = parse_injuries_item(item)
    assert rec is not None
    assert rec.availability_status == "out"
    assert rec.availability_type == "injury"


def test_parse_injuries_skip_without_player():
    assert parse_injuries_item({"team": {"id": 1}}) is None
