"""Test normalizzazione generica mercati odds SportAPI."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_markets_normalize import normalize_all_markets_from_event_odds


def test_normalize_full_time_single_market_three_outcomes():
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
    markets = normalize_all_markets_from_event_odds(payload)
    assert len(markets) == 1
    ft = markets[0]
    assert ft["market_name"] == "Full time"
    assert ft["market_key_guess"] == "match_1x2"
    assert ft["outcomes_count"] == 3
    labels = {o["name"] for o in ft["outcomes"]}
    assert labels == {"1", "X", "2"}


def test_normalize_corners_choice_group_single_row():
    payload = {
        "markets": [
            {
                "marketName": "Corners 2-Way",
                "choiceGroups": [
                    {
                        "choiceGroup": "9,5",
                        "choices": [
                            {"name": "Under", "price": 1.75},
                            {"name": "Over", "price": 2.0},
                        ],
                    },
                ],
            },
        ],
    }
    markets = normalize_all_markets_from_event_odds(payload)
    assert len(markets) == 1
    row = markets[0]
    assert row["market_name"] == "Corners 2-Way"
    assert row["market_key_guess"] == "corners_total"
    assert row["choice_group"] == "9,5"
    assert row["line"] == 9.5
    assert row["outcomes_count"] == 2


def test_over_under_not_standalone_markets():
    payload = {
        "markets": [
            {
                "marketName": "Both teams to score",
                "choices": [
                    {"name": "Yes", "price": 1.7},
                    {"name": "No", "price": 2.1},
                ],
            },
        ],
    }
    markets = normalize_all_markets_from_event_odds(payload)
    names = {m["market_name"] for m in markets}
    assert "Over" not in names
    assert "Under" not in names
    assert "Yes" not in names
    assert "No" not in names
    assert "Both teams to score" in names


def test_normalize_sisal_like_market_set():
    payload = {
        "markets": [
            {"marketName": "Full time", "choices": [{"name": "1", "price": 2.0}, {"name": "X", "price": 3.0}, {"name": "2", "price": 4.0}]},
            {"marketName": "Double chance", "choices": [{"name": "1X", "price": 1.2}, {"name": "X2", "price": 1.3}, {"name": "12", "price": 1.4}]},
            {"marketName": "1st half", "choices": [{"name": "1", "price": 2.5}, {"name": "X", "price": 2.0}, {"name": "2", "price": 3.0}]},
            {"marketName": "Draw no bet", "choices": [{"name": "1", "price": 1.5}, {"name": "2", "price": 2.5}]},
            {"marketName": "Both teams to score", "choices": [{"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.0}]},
            {"marketName": "Match goals", "choices": [{"name": "1+", "price": 1.1}, {"name": "2+", "price": 1.5}]},
            {
                "marketName": "Corners 2-Way",
                "choiceGroups": [{"choiceGroup": "9,5", "choices": [{"name": "Under", "price": 1.75}, {"name": "Over", "price": 2.0}]}],
            },
        ],
    }
    markets = normalize_all_markets_from_event_odds(payload)
    assert len(markets) == 7
    assert {m["market_name"] for m in markets} == {
        "Full time",
        "Double chance",
        "1st half",
        "Draw no bet",
        "Both teams to score",
        "Match goals",
        "Corners 2-Way",
    }


def test_normalize_total_shots_on_target():
    payload = {
        "markets": [
            {
                "marketName": "Total Shots on Target",
                "choices": [
                    {"name": "Over", "price": 1.85, "line": 9.5},
                    {"name": "Under", "price": 1.95, "line": 9.5},
                ],
            },
        ],
    }
    markets = normalize_all_markets_from_event_odds(payload)
    assert len(markets) == 1
    assert markets[0]["market_key_guess"] == "match_total_sot"
