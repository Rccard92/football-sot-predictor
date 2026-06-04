"""Discovery bookmaker/odds — separato da Cecchino e SOT."""

from app.services.bookmakers.bookmaker_constants import (
    MARKET_BTTS,
    MARKET_DOUBLE_CHANCE,
    MARKET_MATCH_WINNER_1X2,
    MARKET_OVER_UNDER_GOALS,
    MARKET_UNKNOWN,
    PROVIDER_SOURCE_API_FOOTBALL,
    PROVIDER_SOURCE_SPORTAPI,
)
from app.services.bookmakers.market_normalize import normalize_market_name

__all__ = [
    "MARKET_BTTS",
    "MARKET_DOUBLE_CHANCE",
    "MARKET_MATCH_WINNER_1X2",
    "MARKET_OVER_UNDER_GOALS",
    "MARKET_UNKNOWN",
    "PROVIDER_SOURCE_API_FOOTBALL",
    "PROVIDER_SOURCE_SPORTAPI",
    "normalize_market_name",
]
