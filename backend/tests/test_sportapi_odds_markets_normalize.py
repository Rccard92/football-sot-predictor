"""Test normalizzazione generica mercati odds SportAPI."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_markets_normalize import normalize_all_markets_from_event_odds


def test_normalize_all_markets_from_payload():
    payload = {
        "markets": [
            {
                "marketName": "Full time",
                "choices": [
                    {"name": "1", "price": 2.1},
                    {"name": "X", "price": 3.4},
                    {"name": "2", "price": 3.8},
                ],
            },
            {
                "marketName": "Total Shots on Target",
                "choices": [
                    {"name": "Over 9.5", "price": 1.85, "line": 9.5},
                    {"name": "Under 9.5", "price": 1.95, "line": 9.5},
                ],
            },
        ],
    }
    markets = normalize_all_markets_from_event_odds(payload)
    assert len(markets) == 2
    names = {m["market_name"] for m in markets}
    assert "Full time" in names
    assert "Total Shots on Target" in names
    sot = next(m for m in markets if m["market_name"] == "Total Shots on Target")
    assert sot["outcomes_count"] == 2
    assert sot.get("market_key_guess") == "match_total_sot"
