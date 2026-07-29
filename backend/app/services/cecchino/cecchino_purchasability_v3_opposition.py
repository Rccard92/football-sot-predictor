"""Famiglie, opposti e contesto collegato Acquistabilità v3.

Famiglie rigorosamente separate: MATCH_WINNER_FT ≠ DOUBLE_CHANCE.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)

V3_OPPOSITION_MAP_VERSION = "cecchino_purchasability_v3_opposition_map_v1"

FAMILY_MATCH_WINNER_FT = "MATCH_WINNER_FT"
FAMILY_GOALS_FT_2_5 = "GOALS_FT_2_5"
FAMILY_DOUBLE_CHANCE = "DOUBLE_CHANCE"

MATCH_WINNER_FT_MARKETS = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
GOALS_FT_2_5_MARKETS = frozenset({SEL_OVER_2_5, SEL_UNDER_2_5})
DOUBLE_CHANCE_MARKETS = frozenset({SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO})

SUPPORTED_V3_MARKETS = frozenset(
    MATCH_WINNER_FT_MARKETS | GOALS_FT_2_5_MARKETS | DOUBLE_CHANCE_MARKETS
)

MARKET_LABELS: dict[str, str] = {
    SEL_HOME: "1",
    SEL_DRAW: "X",
    SEL_AWAY: "2",
    SEL_ONE_X: "1X",
    SEL_X_TWO: "X2",
    SEL_ONE_TWO: "12",
    SEL_OVER_2_5: "Over 2.5",
    SEL_UNDER_2_5: "Under 2.5",
}

_OPPOSITE_FIXED: dict[str, str] = {
    SEL_HOME: SEL_AWAY,
    SEL_AWAY: SEL_HOME,
    SEL_ONE_X: SEL_AWAY,
    SEL_X_TWO: SEL_HOME,
    SEL_ONE_TWO: SEL_DRAW,
    SEL_OVER_2_5: SEL_UNDER_2_5,
    SEL_UNDER_2_5: SEL_OVER_2_5,
}

OPPOSITE_FIXED_MAP = MappingProxyType(dict(_OPPOSITE_FIXED))

# Contesto collegato diagnostico (non concorrente, non usato nello score).
_LINKED_MARKET: dict[str, tuple[str, str]] = {
    SEL_HOME: (SEL_ONE_X, "linked_double_chance_home_cover"),
    SEL_AWAY: (SEL_X_TWO, "linked_double_chance_away_cover"),
    SEL_DRAW: (SEL_ONE_TWO, "linked_double_chance_anti_draw"),
    SEL_OVER_2_5: (SEL_UNDER_2_5, "direct_goals_competitor"),
    SEL_UNDER_2_5: (SEL_OVER_2_5, "direct_goals_competitor"),
    SEL_ONE_X: (SEL_HOME, "linked_match_winner_home"),
    SEL_X_TWO: (SEL_AWAY, "linked_match_winner_away"),
    SEL_ONE_TWO: (SEL_DRAW, "linked_match_winner_draw_complement"),
}

LINKED_MARKET_MAP = MappingProxyType(dict(_LINKED_MARKET))


def market_family_for(market_key: str) -> str | None:
    if market_key in MATCH_WINNER_FT_MARKETS:
        return FAMILY_MATCH_WINNER_FT
    if market_key in GOALS_FT_2_5_MARKETS:
        return FAMILY_GOALS_FT_2_5
    if market_key in DOUBLE_CHANCE_MARKETS:
        return FAMILY_DOUBLE_CHANCE
    return None


def family_markets(family: str) -> frozenset[str]:
    if family == FAMILY_MATCH_WINNER_FT:
        return MATCH_WINNER_FT_MARKETS
    if family == FAMILY_GOALS_FT_2_5:
        return GOALS_FT_2_5_MARKETS
    if family == FAMILY_DOUBLE_CHANCE:
        return DOUBLE_CHANCE_MARKETS
    return frozenset()


def competitors_for_market(market_key: str) -> list[str]:
    """Concorrenti diretti della stessa famiglia (mai 1X2 vs DC)."""
    family = market_family_for(market_key)
    if family is None:
        return []
    return sorted(m for m in family_markets(family) if m != market_key)


def market_label_for(market_key: str) -> str:
    return MARKET_LABELS.get(market_key, market_key)


def period_and_line_for(market_key: str) -> tuple[str | None, float | None]:
    if market_key in MATCH_WINNER_FT_MARKETS or market_key in DOUBLE_CHANCE_MARKETS:
        return "FT", None
    if market_key in GOALS_FT_2_5_MARKETS:
        return "FT", 2.5
    return None, None


def resolve_opposite_selection(
    market_key: str,
    *,
    fair_book_by_market: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Risolve mercato opposto; DRAW usa max fair Book HOME/AWAY."""
    fair = fair_book_by_market or {}
    if market_key == SEL_DRAW:
        home_fair = fair.get(SEL_HOME)
        away_fair = fair.get(SEL_AWAY)
        chosen: str | None = None
        chosen_prob: float | None = None
        if home_fair is not None and away_fair is not None:
            if float(home_fair) >= float(away_fair):
                chosen, chosen_prob = SEL_HOME, float(home_fair)
            else:
                chosen, chosen_prob = SEL_AWAY, float(away_fair)
        elif home_fair is not None:
            chosen, chosen_prob = SEL_HOME, float(home_fair)
        elif away_fair is not None:
            chosen, chosen_prob = SEL_AWAY, float(away_fair)
        return {
            "opposite_market_key": chosen,
            "opposite_fair_probability": chosen_prob,
            "draw_opposite_trace": {
                "fair_book_home": home_fair,
                "fair_book_away": away_fair,
                "selected_lateral": chosen,
                "max_fair_book_probability": chosen_prob,
            },
            "status": "available" if chosen is not None else "unavailable",
        }

    opp = _OPPOSITE_FIXED.get(market_key)
    if opp is None:
        return {
            "opposite_market_key": None,
            "opposite_fair_probability": None,
            "draw_opposite_trace": None,
            "status": "unavailable",
            "reason_code": "purchasability_v3_market_unsupported",
        }
    return {
        "opposite_market_key": opp,
        "opposite_fair_probability": fair.get(opp),
        "draw_opposite_trace": None,
        "status": "available",
    }


def linked_market_key_for(market_key: str) -> tuple[str | None, str | None]:
    entry = _LINKED_MARKET.get(market_key)
    if entry is None:
        return None, None
    return entry[0], entry[1]


def is_v3_supported_market(market_key: str) -> bool:
    return market_key in SUPPORTED_V3_MARKETS
