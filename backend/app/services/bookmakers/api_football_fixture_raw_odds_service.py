"""Raw odds API-Football filtrati per bookmaker whitelist (Bet365/Betfair/Pinnacle)."""

from __future__ import annotations

from typing import Any

from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.bookmakers.bookmaker_constants import (
    MARKET_MATCH_WINNER_1X2,
    MARKET_OVER_UNDER_GOALS,
    PROVIDER_SOURCE_API_FOOTBALL,
)
from app.services.bookmakers.market_normalize import (
    normalize_api_football_market,
    normalize_over_under_selection,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS

_BOOKMAKER_NAMES = {int(b["provider_bookmaker_id"]): str(b["name"]) for b in CECCHINO_BOOKMAKERS}
_DEFAULT_IDS = [int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS]


def _parse_odd(raw: Any) -> float | str | None:
    if raw is None:
        return None
    try:
        v = float(str(raw).replace(",", "."))
        return v if v > 1.0 else str(raw)
    except (TypeError, ValueError):
        return str(raw)


def _extract_bookmaker_bets(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in raw_items:
        for bm in item.get("bookmakers") or []:
            if isinstance(bm, dict):
                return list(bm.get("bets") or [])
    return []


def _sanitize_raw_payload(bets: list[dict[str, Any]]) -> dict[str, Any]:
    return {"bets": bets}


class ApiFootballFixtureRawOddsService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def run(
        self,
        *,
        provider_fixture_id: int,
        provider_source: str = PROVIDER_SOURCE_API_FOOTBALL,
        bookmaker_ids: list[int] | None = None,
        include_raw: bool = True,
    ) -> dict[str, Any]:
        if provider_source != PROVIDER_SOURCE_API_FOOTBALL:
            return {
                "status": "error",
                "message": f"provider_source non supportato: {provider_source}",
            }

        wanted = bookmaker_ids if bookmaker_ids else _DEFAULT_IDS
        wanted = [int(x) for x in wanted if int(x) in _BOOKMAKER_NAMES]

        bookmakers_requested = [
            {"id": bid, "name": _BOOKMAKER_NAMES[bid]} for bid in wanted
        ]

        bookmakers_out: list[dict[str, Any]] = []
        bookmakers_found: list[str] = []
        markets_found: set[str] = set()
        match_winner_found = False
        over_15_found = False
        over_25_found = False
        ou_debug: dict[str, dict[str, Any]] = {
            "over_1_5": {
                "found": False,
                "found_in_bookmakers": [],
                "raw_market_names": [],
                "raw_values": [],
            },
            "over_2_5": {
                "found": False,
                "found_in_bookmakers": [],
                "raw_market_names": [],
                "raw_values": [],
            },
        }

        for bid in wanted:
            name = _BOOKMAKER_NAMES[int(bid)]
            entry: dict[str, Any] = {
                "bookmaker_id": int(bid),
                "bookmaker_name": name,
                "markets": [],
            }
            try:
                raw_items = self._client.get_fixture_odds(int(provider_fixture_id), int(bid))
            except ApiFootballError as exc:
                entry["error"] = str(exc)
                bookmakers_out.append(entry)
                continue

            bets = _extract_bookmaker_bets(raw_items)
            if bets:
                bookmakers_found.append(name)

            markets: list[dict[str, Any]] = []
            for bet in bets:
                if not isinstance(bet, dict):
                    continue
                bet_name = str(bet.get("name") or "")
                raw_value_labels = [
                    str(v.get("value") or "")
                    for v in (bet.get("values") or [])
                    if isinstance(v, dict)
                ]
                normalized = normalize_api_football_market(bet_name, raw_value_labels)
                if normalized != "UNKNOWN":
                    markets_found.add(normalized)
                if normalized == MARKET_MATCH_WINNER_1X2:
                    match_winner_found = True

                values_out: list[dict[str, Any]] = []
                for val in bet.get("values") or []:
                    if not isinstance(val, dict):
                        continue
                    raw_value = str(val.get("value") or "")
                    odd = _parse_odd(val.get("odd"))
                    sel_norm = normalize_over_under_selection(raw_value)
                    values_out.append(
                        {
                            "raw_value": raw_value,
                            "normalized_selection": sel_norm,
                            "odd": odd,
                        },
                    )
                    if sel_norm == SEL_OVER_1_5 and odd is not None:
                        over_15_found = True
                        dbg = ou_debug["over_1_5"]
                        dbg["found"] = True
                        if name not in dbg["found_in_bookmakers"]:
                            dbg["found_in_bookmakers"].append(name)
                        if bet_name not in dbg["raw_market_names"]:
                            dbg["raw_market_names"].append(bet_name)
                        if raw_value not in dbg["raw_values"]:
                            dbg["raw_values"].append(raw_value)
                    if sel_norm == SEL_OVER_2_5 and odd is not None:
                        over_25_found = True
                        dbg = ou_debug["over_2_5"]
                        dbg["found"] = True
                        if name not in dbg["found_in_bookmakers"]:
                            dbg["found_in_bookmakers"].append(name)
                        if bet_name not in dbg["raw_market_names"]:
                            dbg["raw_market_names"].append(bet_name)
                        if raw_value not in dbg["raw_values"]:
                            dbg["raw_values"].append(raw_value)

                markets.append(
                    {
                        "bet_id": str(bet.get("id") or ""),
                        "raw_market_name": bet_name,
                        "normalized_market": normalized,
                        "values": values_out,
                    },
                )

            entry["markets"] = markets
            if include_raw:
                entry["raw_payload"] = _sanitize_raw_payload(bets)
            bookmakers_out.append(entry)

        over_candidates = []
        for key, dbg in ou_debug.items():
            if dbg["found"]:
                over_candidates.append(key)

        return {
            "status": "ok",
            "provider_source": provider_source,
            "provider_fixture_id": int(provider_fixture_id),
            "bookmakers_requested": bookmakers_requested,
            "bookmakers": bookmakers_out,
            "summary": {
                "bookmakers_found": bookmakers_found,
                "markets_found": sorted(markets_found),
                "over_under_candidates": over_candidates,
                "match_winner_found": match_winner_found,
                "over_1_5_found": over_15_found,
                "over_2_5_found": over_25_found,
            },
            "over_under_debug": ou_debug,
        }
