"""Mercati Bet Builder BET-01 — riusa SEL_* e label canoniche, estensibile in BET-04."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_purchasability_v31_opposition import (
    market_family_for,
    market_label_for,
    period_and_line_for,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_target_mapping import SIGNAL_GROUP_TO_MARKET_KEY

# Selection iniziali BET-01 (11). BET-04 estenderà il set KPI.
BET_BUILDER_MARKET_KEYS: tuple[str, ...] = (
    SEL_HOME,
    SEL_DRAW,
    SEL_AWAY,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
    SEL_DRAW_PT,
    SEL_OVER_1_5,
    SEL_UNDER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)

BET_BUILDER_MARKET_KEY_SET: frozenset[str] = frozenset(BET_BUILDER_MARKET_KEYS)

# market_key → signal_group (inverso di SIGNAL_GROUP_TO_MARKET_KEY dove applicabile)
MARKET_KEY_TO_SIGNAL_GROUP: dict[str, str] = {
    market_key: group for group, market_key in SIGNAL_GROUP_TO_MARKET_KEY.items()
}

BALANCE_CONTEXT_MARKETS: frozenset[str] = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
GOAL_INTENSITY_CONTEXT_MARKETS: frozenset[str] = frozenset(
    {SEL_OVER_1_5, SEL_UNDER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5}
)


def market_meta(market_key: str) -> dict[str, Any]:
    period, line = period_and_line_for(market_key)
    return {
        "market_key": market_key,
        "label": market_label_for(market_key),
        "family": market_family_for(market_key),
        "period": period or ("HT" if market_key == SEL_DRAW_PT else "FT"),
        "line": line,
    }


def signal_group_for_market(market_key: str) -> str | None:
    return MARKET_KEY_TO_SIGNAL_GROUP.get(market_key)
