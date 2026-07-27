"""Gruppi concorrenti e mappa opposti Acquistabilità v2."""

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
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

V2_OPPOSITION_MAP_VERSION = "cecchino_purchasability_v2_opposition_map_v1"

SCOPE_OUTCOMES = "OUTCOMES"
SCOPE_GOALS_FT_2_5 = "GOALS_FT_2_5"
SCOPE_GOALS_HT_1_5 = "GOALS_HT_1_5"

PROB_SUBGROUP_MATCH_WINNER = "MATCH_WINNER"
PROB_SUBGROUP_DOUBLE_CHANCE = "DOUBLE_CHANCE"
PROB_SUBGROUP_GOALS_FT = SCOPE_GOALS_FT_2_5
PROB_SUBGROUP_GOALS_HT = SCOPE_GOALS_HT_1_5

OUTCOMES_MARKETS = frozenset(
    {SEL_HOME, SEL_DRAW, SEL_AWAY, SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO}
)
MATCH_WINNER_MARKETS = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
DOUBLE_CHANCE_MARKETS = frozenset({SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO})
GOALS_FT_MARKETS = frozenset({SEL_OVER_2_5, SEL_UNDER_2_5})
GOALS_HT_MARKETS = frozenset({SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5})

SUPPORTED_V2_MARKETS = frozenset(
    OUTCOMES_MARKETS | GOALS_FT_MARKETS | GOALS_HT_MARKETS
)

_OPPOSITE_FIXED: dict[str, str] = {
    SEL_HOME: SEL_AWAY,
    SEL_AWAY: SEL_HOME,
    SEL_ONE_X: SEL_AWAY,
    SEL_X_TWO: SEL_HOME,
    SEL_ONE_TWO: SEL_DRAW,
    SEL_OVER_2_5: SEL_UNDER_2_5,
    SEL_UNDER_2_5: SEL_OVER_2_5,
    SEL_OVER_PT_1_5: SEL_UNDER_PT_1_5,
    SEL_UNDER_PT_1_5: SEL_OVER_PT_1_5,
}

OPPOSITE_FIXED_MAP = MappingProxyType(dict(_OPPOSITE_FIXED))


def decision_group_for_market(market_key: str) -> str | None:
    if market_key in OUTCOMES_MARKETS:
        return SCOPE_OUTCOMES
    if market_key in GOALS_FT_MARKETS:
        return SCOPE_GOALS_FT_2_5
    if market_key in GOALS_HT_MARKETS:
        return SCOPE_GOALS_HT_1_5
    return None


def probability_subgroup_for_market(market_key: str) -> str | None:
    if market_key in MATCH_WINNER_MARKETS:
        return PROB_SUBGROUP_MATCH_WINNER
    if market_key in DOUBLE_CHANCE_MARKETS:
        return PROB_SUBGROUP_DOUBLE_CHANCE
    if market_key in GOALS_FT_MARKETS:
        return PROB_SUBGROUP_GOALS_FT
    if market_key in GOALS_HT_MARKETS:
        return PROB_SUBGROUP_GOALS_HT
    return None


def competitors_for_market(market_key: str) -> list[str]:
    group = decision_group_for_market(market_key)
    if group == SCOPE_OUTCOMES:
        return sorted(m for m in OUTCOMES_MARKETS if m != market_key)
    if group == SCOPE_GOALS_FT_2_5:
        return sorted(m for m in GOALS_FT_MARKETS if m != market_key)
    if group == SCOPE_GOALS_HT_1_5:
        return sorted(m for m in GOALS_HT_MARKETS if m != market_key)
    return []


def probability_competitors_for_market(market_key: str) -> list[str]:
    subgroup = probability_subgroup_for_market(market_key)
    if subgroup == PROB_SUBGROUP_MATCH_WINNER:
        return sorted(m for m in MATCH_WINNER_MARKETS if m != market_key)
    if subgroup == PROB_SUBGROUP_DOUBLE_CHANCE:
        return sorted(m for m in DOUBLE_CHANCE_MARKETS if m != market_key)
    if subgroup == PROB_SUBGROUP_GOALS_FT:
        return sorted(m for m in GOALS_FT_MARKETS if m != market_key)
    if subgroup == PROB_SUBGROUP_GOALS_HT:
        return sorted(m for m in GOALS_HT_MARKETS if m != market_key)
    return []


def profile_scope_for_market(market_key: str) -> str | None:
    return decision_group_for_market(market_key)


def probability_profile_scope_for_market(market_key: str) -> str | None:
    return probability_subgroup_for_market(market_key)


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
            "opposite_selection": chosen,
            "opposite_fair_book_probability": chosen_prob,
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
            "opposite_selection": None,
            "opposite_fair_book_probability": None,
            "draw_opposite_trace": None,
            "status": "unavailable",
            "reason_code": "purchasability_v2_market_unsupported",
        }
    return {
        "opposite_selection": opp,
        "opposite_fair_book_probability": fair.get(opp),
        "draw_opposite_trace": None,
        "status": "available",
    }


def is_v2_supported_market(market_key: str) -> bool:
    return market_key in SUPPORTED_V2_MARKETS
