"""Test normalizzazione bookmakers API-Sports."""

from __future__ import annotations

from app.services.odds_bookmakers_sync_service import _normalize_bookmaker_item


def test_normalize_bookmaker_item_ok():
    out = _normalize_bookmaker_item({"id": 8, "name": "Bet365"})
    assert out is not None
    assert out["id"] == 8
    assert out["name"] == "Bet365"


def test_normalize_bookmaker_item_missing_id():
    assert _normalize_bookmaker_item({"name": "X"}) is None


def test_normalize_bookmaker_item_empty_name():
    assert _normalize_bookmaker_item({"id": 1, "name": ""}) is None


def test_normalize_bookmaker_item_not_dict():
    assert _normalize_bookmaker_item("invalid") is None
