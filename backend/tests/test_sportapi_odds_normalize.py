"""Test normalizzazione odds SportAPI."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_normalize import normalize_sportapi_odds_payload


def test_normalize_nested_dict_with_price():
    payload = {
        "markets": [
            {
                "marketName": "Match Goals",
                "choices": [
                    {"name": "Over 2.5", "price": 1.85, "bookmaker": "Bet365"},
                ],
            },
        ],
    }
    rows, bk = normalize_sportapi_odds_payload(payload, provider_id=1)
    assert len(rows) >= 1
    assert any(r.get("price") for r in rows)
    assert bk == 1


def test_normalize_empty():
    rows, bk = normalize_sportapi_odds_payload(None)
    assert rows == []
    assert bk is None
