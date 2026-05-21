"""Test parse lista provider SportAPI IT/app."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_providers_sync_service import _normalize_list_item
from app.services.sportapi.sportapi_odds_response import unwrap_list


def test_unwrap_list_from_response_key():
    payload = {"response": [{"slug": "sisal-italy-affiliate", "name": "Sisal"}]}
    items = unwrap_list(payload)
    assert len(items) == 1


def test_normalize_list_item():
    norm = _normalize_list_item({"slug": "bet365", "name": "Bet365"}, "IT")
    assert norm is not None
    assert norm["provider_slug"] == "bet365"
    assert norm["provider_name"] == "Bet365"
    assert norm["provider_country"] == "IT"
