"""Test candidati SOT da mercati normalizzati."""

from __future__ import annotations

from app.services.sportapi.sportapi_odds_markets_normalize import normalize_all_markets_from_event_odds
from app.services.sportapi.sportapi_odds_sot_candidates import find_sot_candidate_markets


def test_sot_candidates_exclude_match_goals():
    markets = [
        {
            "market_name": "Match Goals",
            "market_key_guess": "match_goals",
            "outcomes": [{"name": "Over 2.5", "price": 1.9}],
            "outcomes_count": 1,
        },
        {
            "market_name": "Total Shots on Target",
            "market_key_guess": "match_total_sot",
            "line": 9.5,
            "outcomes": [
                {"name": "Over", "price": 1.85, "line": 9.5},
                {"name": "Under", "price": 1.95, "line": 9.5},
            ],
            "outcomes_count": 2,
        },
        {
            "market_name": "Both Teams To Score",
            "market_key_guess": "btts",
            "outcomes": [],
            "outcomes_count": 0,
        },
    ]
    candidates = find_sot_candidate_markets(markets)
    names = {c["market_name"] for c in candidates}
    assert "Match Goals" not in names
    assert "Both Teams To Score" not in names
    assert "Total Shots on Target" in names


def test_corners_not_sot_candidate():
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
    candidates = find_sot_candidate_markets(markets)
    assert len(candidates) == 0
