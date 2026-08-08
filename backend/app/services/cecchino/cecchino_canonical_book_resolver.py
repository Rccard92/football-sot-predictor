"""Risoluzione Book canonica Cecchino: Betfair primary → Bet365 fallback (selection-by-selection)."""

from __future__ import annotations

import math
from typing import Any

from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOK_POLICY_VERSION,
    CECCHINO_FALLBACK_BOOKMAKER,
    CECCHINO_PRIMARY_BOOKMAKER,
    PROVIDER_API_FOOTBALL,
)
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_1X2_FH,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

# Selection KPI Book supportate (stesso set del panel v2)
CANONICAL_BOOK_SELECTION_KEYS: tuple[str, ...] = (
    SEL_HOME,
    SEL_DRAW,
    SEL_AWAY,
    SEL_HOME_PT,
    SEL_DRAW_PT,
    SEL_AWAY_PT,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
    SEL_OVER_1_5,
    SEL_UNDER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_3_5,
    SEL_OVER_PT_0_5,
    SEL_UNDER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_PT_1_5,
)

_MARKET_FOR_KEY: dict[str, str] = {
    SEL_HOME: MARKET_1X2,
    SEL_DRAW: MARKET_1X2,
    SEL_AWAY: MARKET_1X2,
    SEL_HOME_PT: MARKET_1X2_FH,
    SEL_DRAW_PT: MARKET_1X2_FH,
    SEL_AWAY_PT: MARKET_1X2_FH,
    SEL_ONE_X: MARKET_DC,
    SEL_X_TWO: MARKET_DC,
    SEL_ONE_TWO: MARKET_DC,
    SEL_OVER_1_5: MARKET_OU,
    SEL_UNDER_1_5: MARKET_OU,
    SEL_OVER_2_5: MARKET_OU,
    SEL_UNDER_2_5: MARKET_OU,
    SEL_OVER_3_5: MARKET_OU,
    SEL_UNDER_3_5: MARKET_OU,
    SEL_OVER_PT_0_5: MARKET_OU_FH,
    SEL_UNDER_PT_0_5: MARKET_OU_FH,
    SEL_OVER_PT_1_5: MARKET_OU_FH,
    SEL_UNDER_PT_1_5: MARKET_OU_FH,
}

GATE_1X2_KEYS: tuple[str, ...] = (SEL_HOME, SEL_DRAW, SEL_AWAY)


def is_valid_book_odd(value: Any) -> bool:
    """Quota Book valida: numerica, finita, > 1.0."""
    if value is None or isinstance(value, bool):
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 1.0


def normalize_book_odd(value: Any) -> float | None:
    if not is_valid_book_odd(value):
        return None
    return round(float(value), 2)


def market_for_selection(selection_key: str) -> str | None:
    return _MARKET_FOR_KEY.get(selection_key)


def selection_odd_from_markets(
    markets: dict[str, Any] | None,
    selection_key: str,
) -> float | None:
    mkt = _MARKET_FOR_KEY.get(selection_key)
    if not mkt or not markets:
        return None
    block = markets.get(mkt) or {}
    if not isinstance(block, dict):
        return None
    return normalize_book_odd(block.get(selection_key))


def _enrich_provenance(
    prov: dict[str, Any] | None,
    *,
    bookmaker: dict[str, str | int],
    book_fallback_used: bool,
    selection_key: str,
) -> dict[str, Any]:
    base = dict(prov or {})
    base["selection_key"] = selection_key
    base["bookmaker_name"] = str(bookmaker["name"])
    base["provider_bookmaker_id"] = int(bookmaker["provider_bookmaker_id"])
    base["provider_source"] = str(bookmaker.get("provider_source") or PROVIDER_API_FOOTBALL)
    base["book_fallback_used"] = bool(book_fallback_used)
    return base


def resolve_selection_book_odd(
    *,
    selection_key: str,
    primary_markets: dict[str, Any] | None,
    primary_provenance: dict[str, dict[str, Any]] | None,
    fallback_markets: dict[str, Any] | None,
    fallback_provenance: dict[str, dict[str, Any]] | None,
    primary_bookmaker: dict[str, str | int] | None = None,
    fallback_bookmaker: dict[str, str | int] | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    """
    Policy: Betfair primary → Bet365 fallback → N/D.
    Selection-by-selection (mai fixture-by-fixture / best-odds).
    """
    primary = primary_bookmaker or CECCHINO_PRIMARY_BOOKMAKER
    fallback = fallback_bookmaker or CECCHINO_FALLBACK_BOOKMAKER

    primary_odd = selection_odd_from_markets(primary_markets, selection_key)
    if primary_odd is not None:
        prov = _enrich_provenance(
            (primary_provenance or {}).get(selection_key),
            bookmaker=primary,
            book_fallback_used=False,
            selection_key=selection_key,
        )
        return primary_odd, prov

    fallback_odd = selection_odd_from_markets(fallback_markets, selection_key)
    if fallback_odd is not None:
        prov = _enrich_provenance(
            (fallback_provenance or {}).get(selection_key),
            bookmaker=fallback,
            book_fallback_used=True,
            selection_key=selection_key,
        )
        return fallback_odd, prov

    return None, None


def resolve_canonical_markets(
    *,
    primary_markets: dict[str, Any] | None,
    primary_provenance: dict[str, dict[str, Any]] | None,
    fallback_markets: dict[str, Any] | None,
    fallback_provenance: dict[str, dict[str, Any]] | None,
    selection_keys: tuple[str, ...] | list[str] | None = None,
    primary_bookmaker: dict[str, str | int] | None = None,
    fallback_bookmaker: dict[str, str | int] | None = None,
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, Any]], dict[str, Any]]:
    """
    Risolve markets + provenance canonici.

    Returns:
      markets: market -> selection -> odd|None (solo selection presenti)
      provenance_by_selection
      stats: contatori fallback / missing
    """
    keys = tuple(selection_keys or CANONICAL_BOOK_SELECTION_KEYS)
    markets: dict[str, dict[str, float | None]] = {}
    provenance: dict[str, dict[str, Any]] = {}
    fallback_count = 0
    primary_count = 0
    missing_count = 0

    for sk in keys:
        odd, prov = resolve_selection_book_odd(
            selection_key=sk,
            primary_markets=primary_markets,
            primary_provenance=primary_provenance,
            fallback_markets=fallback_markets,
            fallback_provenance=fallback_provenance,
            primary_bookmaker=primary_bookmaker,
            fallback_bookmaker=fallback_bookmaker,
        )
        mkt = _MARKET_FOR_KEY.get(sk)
        if mkt is None:
            continue
        if odd is None:
            missing_count += 1
            continue
        markets.setdefault(mkt, {})[sk] = odd
        if prov:
            provenance[sk] = prov
            if prov.get("book_fallback_used"):
                fallback_count += 1
            else:
                primary_count += 1

    stats = {
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "betfair_primary_used": primary_count > 0,
        "bet365_fallback_used": fallback_count > 0,
        "bet365_fallback_selection_count": fallback_count,
        "betfair_primary_selection_count": primary_count,
        "book_still_missing_after_fallback": missing_count,
    }
    return markets, provenance, stats


def canonical_1x2_complete(
    markets: dict[str, Any] | None,
    provenance: dict[str, dict[str, Any]] | None = None,
) -> tuple[bool, dict[str, float], dict[str, str]]:
    """Verifica HOME/DRAW/AWAY canonici. Ritorna (ok, odds, selection_sources)."""
    odds: dict[str, float] = {}
    sources: dict[str, str] = {}
    prov = provenance or {}
    for sk in GATE_1X2_KEYS:
        val = selection_odd_from_markets(markets, sk)
        if val is None:
            return False, odds, sources
        odds[sk] = val
        p = prov.get(sk) or {}
        sources[sk] = str(p.get("bookmaker_name") or "Book")
    return True, odds, sources
