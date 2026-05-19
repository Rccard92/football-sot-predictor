"""Helper fetch/filter/dedup injuries multi-source."""

from app.services.availability.availability_injuries_sources import (
    SOURCE_DETAIL_FIXTURE_DIRECT,
    SOURCE_DETAIL_IDS_BATCH,
    SOURCE_DETAIL_LEAGUE_SEASON_FILTERED,
    dedupe_key,
    filter_items_for_upcoming,
    item_api_fixture_id,
    merge_sourced_items,
)


def _item(api_fx: int, team: int, player: int) -> dict:
    return {
        "player": {"id": player, "name": "P"},
        "team": {"id": team, "name": "T"},
        "fixture": {"id": api_fx, "date": "2025-05-20T18:00:00+00:00"},
    }


def test_filter_items_for_upcoming():
    upcoming = {100, 200}
    items = [_item(100, 1, 10), _item(999, 1, 11), _item(200, 2, 12)]
    out = filter_items_for_upcoming(items, upcoming)
    assert len(out) == 2
    assert {item_api_fixture_id(x) for x in out} == {100, 200}


def test_merge_priority_ids_over_league():
    a = _item(100, 1, 10)
    b = {**_item(100, 1, 10), "player": {"id": 10, "name": "P2", "reason": "Other"}}
    merged = merge_sourced_items(
        [
            ([b], SOURCE_DETAIL_LEAGUE_SEASON_FILTERED),
            ([a], SOURCE_DETAIL_IDS_BATCH),
        ],
    )
    assert len(merged) == 1
    assert merged[0][1] == SOURCE_DETAIL_IDS_BATCH


def test_dedupe_key_requires_ids():
    assert dedupe_key({"player": {}, "team": {}, "fixture": {}}) is None
    assert dedupe_key(_item(1, 2, 3)) == (1, 2, 3)
