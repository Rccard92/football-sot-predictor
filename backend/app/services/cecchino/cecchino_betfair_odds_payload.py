"""Costruzione payload quote Betfair da raw API-Football o snapshot."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_betfair_odds_mapping import (
    parsed_rows_to_markets_and_provenance,
    validate_betfair_kpi_odds_mapping,
)
from app.services.cecchino.cecchino_bookmaker_derive import derive_double_chance_from_1x2
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_1X2_FH,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)

_BETFAIR_ID = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
_WANTED_MARKETS = [MARKET_1X2, MARKET_1X2_FH, MARKET_DC, MARKET_OU, MARKET_OU_FH]


def _build_markets_from_parsed(
    markets_raw: dict[str, dict[str, float]],
    provenance: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, bool], str, dict[str, dict[str, Any]]]:
    m1 = markets_raw.get(MARKET_1X2, {})
    home = m1.get(SEL_HOME)
    draw = m1.get(SEL_DRAW)
    away = m1.get(SEL_AWAY)

    if home is None or draw is None or away is None:
        if any(x is not None for x in (home, draw, away)):
            return {}, {}, "partial", provenance
        return {}, {}, "not_available", provenance

    derived = derive_double_chance_from_1x2(home, draw, away)
    dc_raw = markets_raw.get(MARKET_DC, {})

    dc_derived: dict[str, bool] = {}
    dc_out: dict[str, float | None] = {}
    prov_out = dict(provenance)

    for sk in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
        raw_val = dc_raw.get(sk)
        if raw_val is not None:
            dc_out[sk] = raw_val
            dc_derived[sk] = False
        else:
            dc_out[sk] = derived.get(sk)
            dc_derived[sk] = True
            if derived.get(sk) is not None:
                prov_out[sk] = {
                    "raw_market_name": "Match Winner",
                    "bet_id": None,
                    "raw_value": None,
                    "selection_key": sk,
                    "source": "derived_from_betfair_1x2",
                    "derived_formula": f"1/(prob_sum) from 1X2",
                }

    markets: dict[str, Any] = {
        MARKET_1X2: {SEL_HOME: home, SEL_DRAW: draw, SEL_AWAY: away},
        MARKET_DC: dc_out,
    }
    ou = markets_raw.get(MARKET_OU, {})
    if ou:
        markets[MARKET_OU] = dict(ou)
    ou_fh = markets_raw.get(MARKET_OU_FH, {})
    if ou_fh:
        markets[MARKET_OU_FH] = dict(ou_fh)
    fh_1x2 = markets_raw.get(MARKET_1X2_FH, {})
    if fh_1x2:
        markets[MARKET_1X2_FH] = dict(fh_1x2)

    return markets, dc_derived, "available", prov_out


def build_betfair_payload_from_raw(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]] | None,
    *,
    source: str = "betfair",
    home_team_name: str | None = None,
    away_team_name: str | None = None,
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
            "provenance_by_selection": {},
        }

    mapping_warnings: list[str] = []
    parsed, missing = parse_api_football_odds_response(
        raw,
        requested_markets=_WANTED_MARKETS,
        strict_betfair_kpi=True,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        mapping_warnings=mapping_warnings,
    )
    markets_raw, provenance = parsed_rows_to_markets_and_provenance(parsed)
    markets, dc_derived, status, provenance = _build_markets_from_parsed(markets_raw, provenance)

    warnings: list[str] = list(mapping_warnings)
    if missing:
        warnings.append(f"mercati_mancanti:{','.join(missing)}")
    if status == "available":
        warnings.extend(validate_betfair_kpi_odds_mapping(markets, provenance, dc_derived))

    bookmakers_list = [
        {
            "bookmaker_name": CECCHINO_BOOKMAKER["name"],
            "provider_bookmaker_id": _BETFAIR_ID,
            "status": status,
            "markets": markets,
            "dc_derived": dc_derived,
            "provenance_by_selection": provenance,
        },
    ]

    return {
        "provider_source": PROVIDER_API_FOOTBALL,
        "bookmakers": bookmakers_list,
        "status": status,
        "warnings": warnings,
        "odds_source": source,
        "provenance_by_selection": provenance,
    }


def build_betfair_payload_from_snapshot(
    odds_snapshot: dict[str, Any] | None,
    *,
    source: str = "cached_betfair_odds",
    home_team_name: str | None = None,
    away_team_name: str | None = None,
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
            prov = {
                SEL_HOME: {"source": "betfair_raw_match_winner", "raw_market_name": "snapshot_1x2"},
                SEL_DRAW: {"source": "betfair_raw_match_winner", "raw_market_name": "snapshot_1x2"},
                SEL_AWAY: {"source": "betfair_raw_match_winner", "raw_market_name": "snapshot_1x2"},
                SEL_ONE_X: {"source": "derived_from_betfair_1x2"},
                SEL_X_TWO: {"source": "derived_from_betfair_1x2"},
                SEL_ONE_TWO: {"source": "derived_from_betfair_1x2"},
            }
            return {
                "provider_source": PROVIDER_API_FOOTBALL,
                "bookmakers": [
                    {
                        "bookmaker_name": CECCHINO_BOOKMAKER["name"],
                        "provider_bookmaker_id": _BETFAIR_ID,
                        "status": "available",
                        "markets": markets,
                        "dc_derived": {SEL_ONE_X: True, SEL_X_TWO: True, SEL_ONE_TWO: True},
                        "provenance_by_selection": prov,
                    },
                ],
                "status": "available",
                "warnings": ["snapshot_1x2_only_no_ou"],
                "odds_source": source,
                "provenance_by_selection": prov,
            }
        return build_betfair_payload_from_raw(None, source=source)

    return build_betfair_payload_from_raw(
        {_BETFAIR_ID: list(raw)},
        source=source,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )
