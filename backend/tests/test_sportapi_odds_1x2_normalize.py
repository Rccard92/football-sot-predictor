"""Test estrazione mercato 1X2 da payload SportAPI."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_1x2_normalize import extract_1x2_from_event_odds


def test_extract_1x2_match_winner():
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
        ],
    }
    out = extract_1x2_from_event_odds(payload)
    assert out["market_found"] is True
    assert out["home_odd"] == 2.1
    assert out["draw_odd"] == 3.4
    assert out["away_odd"] == 3.8
    assert out["market_key"] == "1x2"


def test_extract_1x2_missing():
    out = extract_1x2_from_event_odds({"markets": [{"marketName": "Over 2.5", "choices": []}]})
    assert out["market_found"] is False
    assert "Over 2.5" in (out.get("available_markets") or [])
