"""Test estrazione mercato 1X2 da payload SportAPI."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_1x2_normalize import (
    extract_1x2_from_event_odds,
    row_status_from_normalization,
)


def test_extract_1x2_full_time_price():
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
    assert out["market_matched"] is True
    assert out["normalization_status"] == "ok"
    assert out["outcomes_complete"] is True
    assert out["home_odd"] == 2.1
    assert out["draw_odd"] == 3.4
    assert out["away_odd"] == 3.8
    assert out["market_key"] == "1x2"
    assert out["market_name_original"] == "Full time"


def test_extract_1x2_fractional_value():
    payload = {
        "markets": [
            {
                "marketName": "Full time",
                "choices": [
                    {"name": "1", "fractionalValue": "11/10"},
                    {"name": "X", "fractionalValue": "5/2"},
                    {"name": "2", "fractionalValue": "3/1"},
                ],
            },
        ],
    }
    out = extract_1x2_from_event_odds(payload)
    assert out["normalization_status"] == "ok"
    assert out["home_odd"] is not None
    assert out["draw_odd"] is not None
    assert out["away_odd"] is not None


def test_extract_1x2_team_names_positional():
    payload = {
        "markets": [
            {
                "marketName": "Full time",
                "choices": [
                    {"name": "Fiorentina", "decimalOdd": 2.05},
                    {"name": "Draw", "decimalOdd": 3.5},
                    {"name": "Atalanta", "decimalOdd": 3.9},
                ],
            },
        ],
    }
    out = extract_1x2_from_event_odds(payload)
    assert out["normalization_status"] == "ok"
    assert out["home_odd"] == 2.05
    assert out["draw_odd"] == 3.5
    assert out["away_odd"] == 3.9


def test_extract_1x2_incomplete():
    payload = {
        "markets": [
            {
                "marketName": "Full time",
                "choices": [
                    {"name": "1", "price": 2.1},
                    {"name": "X", "price": 3.4},
                ],
            },
        ],
    }
    out = extract_1x2_from_event_odds(payload)
    assert out["market_matched"] is True
    assert out["normalization_status"] == "incomplete"
    assert out["outcomes_complete"] is False


def test_extract_winner_alias():
    payload = {
        "markets": [
            {
                "marketName": "Winner",
                "choices": [
                    {"name": "1", "price": 1.9},
                    {"name": "X", "price": 3.2},
                    {"name": "2", "price": 4.1},
                ],
            },
        ],
    }
    out = extract_1x2_from_event_odds(payload)
    assert out["market_matched"] is True
    assert out["market_key"] == "1x2"


def test_extract_missing_market():
    out = extract_1x2_from_event_odds({"markets": [{"marketName": "Over 2.5", "choices": []}]})
    assert out["normalization_status"] == "not_found"
    assert "Over 2.5" in (out.get("available_markets") or [])


def test_row_status_from_normalization():
    assert row_status_from_normalization({"normalization_status": "ok"}) == "ok"
    assert row_status_from_normalization({"normalization_status": "incomplete"}) == "incomplete_1x2"
    assert row_status_from_normalization({"normalization_status": "not_found"}) == "no_1x2"
