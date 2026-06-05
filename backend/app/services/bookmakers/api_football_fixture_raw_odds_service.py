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
    MAIN_FT_OU_RAW_NAME,
    is_main_first_half_goals_over_under,
    is_main_full_time_goals_over_under,
    normalize_api_football_market,
    normalize_first_half_over_under_selection,
    normalize_over_under_selection,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
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


def _empty_ou_debug_entry() -> dict[str, Any]:
    return {
        "found": False,
        "found_in_bookmakers": [],
        "raw_market_name": None,
        "bet_id": None,
        "raw_values": [],
    }


def _mark_ou_found(
    dbg: dict[str, Any],
    *,
    bookmaker_name: str,
    bet_name: str,
    bet_id: Any,
    raw_value: str,
) -> None:
    dbg["found"] = True
    if bookmaker_name not in dbg["found_in_bookmakers"]:
        dbg["found_in_bookmakers"].append(bookmaker_name)
    if dbg["raw_market_name"] is None:
        dbg["raw_market_name"] = bet_name
    if dbg["bet_id"] is None:
        dbg["bet_id"] = str(bet_id) if bet_id is not None else None
    if raw_value not in dbg["raw_values"]:
        dbg["raw_values"].append(raw_value)


def _append_rejected(
    rejected: list[dict[str, Any]],
    *,
    bookmaker_name: str,
    bet_name: str,
    bet_id: Any,
    raw_value: str,
    selection_key: str,
    reason: str,
) -> None:
    rejected.append(
        {
            "bookmaker_name": bookmaker_name,
            "raw_market_name": bet_name,
            "bet_id": str(bet_id) if bet_id is not None else None,
            "raw_value": raw_value,
            "selection_key": selection_key,
            "reason": reason,
        },
    )


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
        ft_debug: dict[str, Any] = {
            "OVER_1_5": _empty_ou_debug_entry(),
            "OVER_2_5": _empty_ou_debug_entry(),
            "rejected_from_markets": [],
        }
        fh_debug: dict[str, Any] = {
            "OVER_PT_0_5": _empty_ou_debug_entry(),
            "OVER_PT_1_5": _empty_ou_debug_entry(),
            "rejected_from_markets": [],
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
                bet_id = bet.get("id")
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

                is_ft_ou = is_main_full_time_goals_over_under(bet_name, bet_id)
                is_fh_ou = is_main_first_half_goals_over_under(bet_name)

                values_out: list[dict[str, Any]] = []
                for val in bet.get("values") or []:
                    if not isinstance(val, dict):
                        continue
                    raw_value = str(val.get("value") or "")
                    odd = _parse_odd(val.get("odd"))
                    sel_norm = normalize_over_under_selection(raw_value)
                    sel_pt = normalize_first_half_over_under_selection(raw_value)
                    values_out.append(
                        {
                            "raw_value": raw_value,
                            "normalized_selection": sel_norm,
                            "normalized_selection_first_half": sel_pt,
                            "odd": odd,
                            "strict_full_time": is_ft_ou,
                            "strict_first_half": is_fh_ou,
                        },
                    )

                    if odd is None:
                        continue

                    if sel_norm == SEL_OVER_1_5:
                        if is_ft_ou:
                            _mark_ou_found(
                                ft_debug["OVER_1_5"],
                                bookmaker_name=name,
                                bet_name=MAIN_FT_OU_RAW_NAME,
                                bet_id=bet_id,
                                raw_value=raw_value,
                            )
                        else:
                            _append_rejected(
                                ft_debug["rejected_from_markets"],
                                bookmaker_name=name,
                                bet_name=bet_name,
                                bet_id=bet_id,
                                raw_value=raw_value,
                                selection_key=SEL_OVER_1_5,
                                reason="not_main_full_time_goals_over_under",
                            )
                    if sel_norm == SEL_OVER_2_5:
                        if is_ft_ou:
                            _mark_ou_found(
                                ft_debug["OVER_2_5"],
                                bookmaker_name=name,
                                bet_name=MAIN_FT_OU_RAW_NAME,
                                bet_id=bet_id,
                                raw_value=raw_value,
                            )
                        else:
                            _append_rejected(
                                ft_debug["rejected_from_markets"],
                                bookmaker_name=name,
                                bet_name=bet_name,
                                bet_id=bet_id,
                                raw_value=raw_value,
                                selection_key=SEL_OVER_2_5,
                                reason="not_main_full_time_goals_over_under",
                            )

                    if sel_pt == SEL_OVER_PT_0_5:
                        if is_fh_ou:
                            _mark_ou_found(
                                fh_debug["OVER_PT_0_5"],
                                bookmaker_name=name,
                                bet_name=bet_name,
                                bet_id=bet_id,
                                raw_value=raw_value,
                            )
                        else:
                            _append_rejected(
                                fh_debug["rejected_from_markets"],
                                bookmaker_name=name,
                                bet_name=bet_name,
                                bet_id=bet_id,
                                raw_value=raw_value,
                                selection_key=SEL_OVER_PT_0_5,
                                reason="not_main_first_half_goals_over_under",
                            )
                    if sel_pt == SEL_OVER_PT_1_5:
                        if is_fh_ou:
                            _mark_ou_found(
                                fh_debug["OVER_PT_1_5"],
                                bookmaker_name=name,
                                bet_name=bet_name,
                                bet_id=bet_id,
                                raw_value=raw_value,
                            )
                        else:
                            _append_rejected(
                                fh_debug["rejected_from_markets"],
                                bookmaker_name=name,
                                bet_name=bet_name,
                                bet_id=bet_id,
                                raw_value=raw_value,
                                selection_key=SEL_OVER_PT_1_5,
                                reason="not_main_first_half_goals_over_under",
                            )

                markets.append(
                    {
                        "bet_id": str(bet.get("id") or ""),
                        "raw_market_name": bet_name,
                        "normalized_market": normalized,
                        "strict_full_time": is_ft_ou,
                        "strict_first_half": is_fh_ou,
                        "values": values_out,
                    },
                )

            entry["markets"] = markets
            if include_raw:
                entry["raw_payload"] = _sanitize_raw_payload(bets)
            bookmakers_out.append(entry)

        over_candidates = []
        for key in ("OVER_1_5", "OVER_2_5"):
            if ft_debug[key]["found"]:
                over_candidates.append(key.lower())
        for key in ("OVER_PT_0_5", "OVER_PT_1_5"):
            if fh_debug[key]["found"]:
                over_candidates.append(key.lower())

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
                "over_1_5_found": ft_debug["OVER_1_5"]["found"],
                "over_2_5_found": ft_debug["OVER_2_5"]["found"],
                "over_pt_0_5_found": fh_debug["OVER_PT_0_5"]["found"],
                "over_pt_1_5_found": fh_debug["OVER_PT_1_5"]["found"],
            },
            "over_under_full_time_debug": ft_debug,
            "over_under_first_half_debug": fh_debug,
        }
