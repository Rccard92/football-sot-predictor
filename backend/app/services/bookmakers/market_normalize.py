"""Normalizzazione nomi mercato provider → enum discovery."""

from __future__ import annotations

import re

from app.services.bookmakers.bookmaker_constants import (
    MARKET_BTTS,
    MARKET_DOUBLE_CHANCE,
    MARKET_MATCH_WINNER_1X2,
    MARKET_OVER_UNDER_GOALS,
    MARKET_UNKNOWN,
)

_1X2_PATTERNS = re.compile(
    r"(?:^|\b)(?:1\s*x\s*2|1x2|match\s*winner|full\s*time|fulltime|regular\s*time|"
    r"winner|esito\s*finale|risultato\s*finale|match\s*result)(?:\b|$)",
    re.IGNORECASE,
)
_DC_PATTERNS = re.compile(
    r"(?:double\s*chance|doppia\s*chance|chance\s*doppia)",
    re.IGNORECASE,
)
_OU_PATTERNS = re.compile(
    r"(?:over\s*/?\s*under|o/u|total\s*goals|totale\s*gol|goal\s*line|goals\s*over)",
    re.IGNORECASE,
)
_BTTS_PATTERNS = re.compile(
    r"(?:both\s*teams?\s*to\s*score|btts|gol\s*/\s*no\s*gol|gg/ng)",
    re.IGNORECASE,
)


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def normalize_market_name(raw_name: str | None, *, raw_market_key: str | None = None) -> str:
    """Mappa nome mercato grezzo a normalized_market enum."""
    if raw_market_key:
        key = raw_market_key.strip().lower().replace("-", "_")
        legacy_map = {
            "match_1x2": MARKET_MATCH_WINNER_1X2,
            "double_chance": MARKET_DOUBLE_CHANCE,
            "match_goals": MARKET_OVER_UNDER_GOALS,
            "btts": MARKET_BTTS,
        }
        if key in legacy_map:
            return legacy_map[key]

    if not raw_name or not str(raw_name).strip():
        return MARKET_UNKNOWN

    n = _norm(str(raw_name))
    if _1X2_PATTERNS.search(n):
        return MARKET_MATCH_WINNER_1X2
    if _DC_PATTERNS.search(n):
        return MARKET_DOUBLE_CHANCE
    if _OU_PATTERNS.search(n):
        return MARKET_OVER_UNDER_GOALS
    if _BTTS_PATTERNS.search(n):
        return MARKET_BTTS
    return MARKET_UNKNOWN
