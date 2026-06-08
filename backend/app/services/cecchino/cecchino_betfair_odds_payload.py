"""Costruzione payload quote Betfair da raw API-Football o snapshot."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_derive import derive_double_chance_from_1x2
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)

_BETFAIR_ID = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
_WANTED_MARKETS = [MARKET_1X2, MARKET_DC, MARKET_OU, MARKET_OU_FH]


def _parsed_rows_to_markets_map(parsed: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    by_mkt: dict[str, dict[str, float]] = {}
    for pr in parsed:
        mkt = pr["normalized_market"]
        sk = pr["selection_key"]
        by_mkt.setdefault(mkt, {})[sk] = float(pr["odds_value"])
    return by_mkt


def _build_markets_from_parsed(
    markets_raw: dict[str, dict[str, float]],
) -> tuple[dict[str, Any], dict[str, bool], str]:
    m1 = markets_raw.get(MARKET_1X2, {})
    home = m1.get(SEL_HOME)
    draw = m1.get(SEL_DRAW)
    away = m1.get(SEL_AWAY)

    if home is None or draw is None or away is None:
        if any(x is not None for x in (home, draw, away)):
            return {}, {}, "partial"
        return {}, {}, "not_available"

    derived = derive_double_chance_from_1x2(home, draw, away)
    dc_raw = markets_raw.get(MARKET_DC, {})

    dc_derived = {
        SEL_ONE_X: SEL_ONE_X not in dc_raw or dc_raw.get(SEL_ONE_X) is None,
        SEL_X_TWO: SEL_X_TWO not in dc_raw or dc_raw.get(SEL_X_TWO) is None,
        SEL_ONE_TWO: SEL_ONE_TWO not in dc_raw or dc_raw.get(SEL_ONE_TWO) is None,
    }

    markets: dict[str, Any] = {
        MARKET_1X2: {SEL_HOME: home, SEL_DRAW: draw, SEL_AWAY: away},
        MARKET_DC: {
            SEL_ONE_X: dc_raw.get(SEL_ONE_X) or derived.get(SEL_ONE_X),
            SEL_X_TWO: dc_raw.get(SEL_X_TWO) or derived.get(SEL_X_TWO),
            SEL_ONE_TWO: dc_raw.get(SEL_ONE_TWO) or derived.get(SEL_ONE_TWO),
        },
    }
    ou = markets_raw.get(MARKET_OU, {})
    if ou:
        markets[MARKET_OU] = dict(ou)
    ou_fh = markets_raw.get(MARKET_OU_FH, {})
    if ou_fh:
        markets[MARKET_OU_FH] = dict(ou_fh)

    return markets, dc_derived, "available"


def build_betfair_payload_from_raw(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]] | None,
    *,
    source: str = "betfair",
) -> dict[str, Any]:
    """
    Costruisce payload Betfair da odds_by_bookmaker in memoria.
    source: betfair | cached_betfair_odds
    """
    raw = (odds_by_bookmaker or {}).get(_BETFAIR_ID) or []
    if not raw:
        return {
            "provider_source": PROVIDER_API_FOOTBALL,
            "bookmakers": [],
            "status": "not_available",
            "warnings": ["Betfair raw odds mancanti"],
            "odds_source": source,
        }

    parsed, missing = parse_api_football_odds_response(raw, requested_markets=_WANTED_MARKETS)
    markets_raw = _parsed_rows_to_markets_map(parsed)
    markets, dc_derived, status = _build_markets_from_parsed(markets_raw)

    warnings: list[str] = []
    if missing:
        warnings.append(f"mercati_mancanti:{','.join(missing)}")

    bookmakers_list = [
        {
            "bookmaker_name": CECCHINO_BOOKMAKER["name"],
            "provider_bookmaker_id": _BETFAIR_ID,
            "status": status,
            "markets": markets,
            "dc_derived": dc_derived,
        },
    ]

    return {
        "provider_source": PROVIDER_API_FOOTBALL,
        "bookmakers": bookmakers_list,
        "status": status,
        "warnings": warnings,
        "odds_source": source,
    }


def build_betfair_payload_from_snapshot(
    odds_snapshot: dict[str, Any] | None,
    *,
    source: str = "cached_betfair_odds",
) -> dict[str, Any]:
    """Costruisce payload Betfair da odds_snapshot_json.raw_by_bookmaker_id."""
    if not odds_snapshot:
        return build_betfair_payload_from_raw(None, source=source)

    raw_map = odds_snapshot.get("raw_by_bookmaker_id") or {}
    raw = raw_map.get(str(_BETFAIR_ID)) or raw_map.get(_BETFAIR_ID)
    if not raw:
        books = odds_snapshot.get("bookmakers") or {}
        bf = books.get(CECCHINO_BOOKMAKER["name"]) or books.get("Betfair")
        if isinstance(bf, dict) and all(bf.get(k) is not None for k in ("HOME", "DRAW", "AWAY")):
            markets = {
                MARKET_1X2: {
                    SEL_HOME: float(bf["HOME"]),
                    SEL_DRAW: float(bf["DRAW"]),
                    SEL_AWAY: float(bf["AWAY"]),
                },
            }
            derived = derive_double_chance_from_1x2(
                markets[MARKET_1X2][SEL_HOME],
                markets[MARKET_1X2][SEL_DRAW],
                markets[MARKET_1X2][SEL_AWAY],
            )
            markets[MARKET_DC] = derived
            return {
                "provider_source": PROVIDER_API_FOOTBALL,
                "bookmakers": [
                    {
                        "bookmaker_name": CECCHINO_BOOKMAKER["name"],
                        "provider_bookmaker_id": _BETFAIR_ID,
                        "status": "available",
                        "markets": markets,
                    },
                ],
                "status": "available",
                "warnings": ["snapshot_1x2_only_no_ou"],
                "odds_source": source,
            }
        return build_betfair_payload_from_raw(None, source=source)

    return build_betfair_payload_from_raw({_BETFAIR_ID: list(raw)}, source=source)
