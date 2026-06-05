"""Normalizzazione nomi mercato provider → enum discovery."""

from __future__ import annotations

import re
from typing import Any

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


SEL_OVER_1_5 = "OVER_1_5"
SEL_UNDER_1_5 = "UNDER_1_5"
SEL_OVER_2_5 = "OVER_2_5"
SEL_UNDER_2_5 = "UNDER_2_5"
SEL_OVER_PT_0_5 = "OVER_PT_0_5"
SEL_OVER_PT_1_5 = "OVER_PT_1_5"
SEL_UNKNOWN = "UNKNOWN"

MAIN_FT_OU_RAW_NAME = "Goals Over/Under"
MAIN_FH_OU_RAW_NAMES = frozenset(
    {
        "Goals Over/Under First Half",
        "Goals Over/Under - First Half",
    },
)
API_FOOTBALL_BET_ID_GOALS_OU = 5

_OU_VALUE_HINT = re.compile(r"\b(?:over|under|o/u)\b", re.IGNORECASE)
_LINE_05 = re.compile(r"0[,.]5")
_LINE_15 = re.compile(r"1[,.]5")
_LINE_25 = re.compile(r"2[,.]5")


def is_main_full_time_goals_over_under(raw_market_name: str | None, bet_id: Any) -> bool:
    """True solo per Goals Over/Under full match con bet_id=5."""
    return raw_market_name == MAIN_FT_OU_RAW_NAME and str(bet_id) == str(API_FOOTBALL_BET_ID_GOALS_OU)


def is_main_first_half_goals_over_under(raw_market_name: str | None) -> bool:
    """True solo per Goals Over/Under First Half (varianti ammesse)."""
    return raw_market_name in MAIN_FH_OU_RAW_NAMES


def normalize_over_under_selection(raw_value: str | None) -> str:
    """Mappa value grezzo API-Football a selection enum Over/Under."""
    if not raw_value or not str(raw_value).strip():
        return SEL_UNKNOWN
    n = _norm(str(raw_value))
    is_over = "over" in n
    is_under = "under" in n
    if not is_over and not is_under:
        return SEL_UNKNOWN
    has_15 = bool(_LINE_15.search(n))
    has_25 = bool(_LINE_25.search(n))
    if is_over and has_15:
        return SEL_OVER_1_5
    if is_under and has_15:
        return SEL_UNDER_1_5
    if is_over and has_25:
        return SEL_OVER_2_5
    if is_under and has_25:
        return SEL_UNDER_2_5
    return SEL_UNKNOWN


def normalize_first_half_over_under_selection(raw_value: str | None) -> str:
    """Mappa value grezzo API-Football a selection enum Over primo tempo."""
    if not raw_value or not str(raw_value).strip():
        return SEL_UNKNOWN
    n = _norm(str(raw_value))
    if "over" not in n:
        return SEL_UNKNOWN
    has_05 = bool(_LINE_05.search(n))
    has_15 = bool(_LINE_15.search(n))
    if has_05:
        return SEL_OVER_PT_0_5
    if has_15:
        return SEL_OVER_PT_1_5
    return SEL_UNKNOWN


def normalize_api_football_market(
    raw_market_name: str | None,
    raw_values: list[str] | None = None,
) -> str:
    """Normalizza nome mercato API-Football; rifiuta OU ambiguo senza values compatibili."""
    norm = normalize_market_name(raw_market_name)
    if norm != MARKET_OVER_UNDER_GOALS:
        return norm
    if not raw_values:
        return norm
    hints = [_norm(v) for v in raw_values if v]
    if not hints:
        return norm
    if any(_OU_VALUE_HINT.search(v) for v in hints):
        return MARKET_OVER_UNDER_GOALS
    return MARKET_UNKNOWN
