"""Test normalizzazione mercati bookmaker."""

from __future__ import annotations

from app.services.bookmakers.bookmaker_constants import (
    MARKET_MATCH_WINNER_1X2,
    MARKET_OVER_UNDER_GOALS,
    MARKET_UNKNOWN,
)
from app.services.bookmakers.market_normalize import (
    normalize_api_football_market,
    normalize_market_name,
    normalize_over_under_selection,
    SEL_OVER_1_5,
)


def test_1x2_name_maps_to_match_winner():
    assert normalize_market_name("Full Time Result") == MARKET_MATCH_WINNER_1X2
    assert normalize_market_name("1X2") == MARKET_MATCH_WINNER_1X2


def test_legacy_key_match_1x2():
    assert normalize_market_name("foo", raw_market_key="match_1x2") == MARKET_MATCH_WINNER_1X2


def test_ambiguous_name_is_unknown():
    assert normalize_market_name("Special combo boost") == MARKET_UNKNOWN
    assert normalize_market_name("") == MARKET_UNKNOWN


def test_goals_over_under_via_api_football_helper():
    assert normalize_api_football_market("Goals Over/Under", ["Over 1.5"]) == MARKET_OVER_UNDER_GOALS


def test_match_goals_without_ou_values_stays_unknown():
    assert normalize_api_football_market("Match goals", ["1+", "2+"]) == MARKET_UNKNOWN


def test_over_selection_helper():
    assert normalize_over_under_selection("Over 1.5") == SEL_OVER_1_5
