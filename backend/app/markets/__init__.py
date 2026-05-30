"""Market package — registry stub (Step A)."""

from app.markets.registry import (
    MARKET_CARDS,
    MARKET_CORNERS,
    MARKET_FOULS,
    MARKET_GOALS,
    MARKET_REGISTRY,
    MARKET_SHOTS_ON_TARGET,
    MARKET_TOTAL_SHOTS,
    MarketSpec,
    get_market,
    list_active_markets,
)

__all__ = [
    "MARKET_CARDS",
    "MARKET_CORNERS",
    "MARKET_FOULS",
    "MARKET_GOALS",
    "MARKET_REGISTRY",
    "MARKET_SHOTS_ON_TARGET",
    "MARKET_TOTAL_SHOTS",
    "MarketSpec",
    "get_market",
    "list_active_markets",
]
