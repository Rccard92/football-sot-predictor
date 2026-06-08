"""Export JSON completo mercati Betfair per singola fixture."""

from __future__ import annotations

from typing import Any

from app.services.bookmakers.market_normalize import (
    is_main_first_half_goals_over_under,
    is_main_full_time_goals_over_under,
    normalize_api_football_market,
    normalize_first_half_over_under_selection,
    normalize_over_under_selection,
)
from app.services.cecchino.cecchino_betfair_odds_mapping import (
    is_strict_double_chance_market,
    is_strict_match_winner_market,
    normalize_double_chance_selection,
    normalize_match_winner_selection,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, MARKET_DC, MARKET_OU, MARKET_OU_FH

_BETFAIR_ID = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])

_MANUAL_NOTE = (
    "Confrontare queste quote con app Betfair. Se differiscono, il feed API-Football "
    "potrebbe essere in ritardo o usare snapshot diverso."
)


def _normalize_market_label(bet_name: str, bet_id: Any) -> str | None:
    if is_strict_match_winner_market(bet_name, bet_id):
        return MARKET_1X2
    if is_strict_double_chance_market(bet_name):
        return MARKET_DC
    if is_main_full_time_goals_over_under(bet_name, bet_id):
        return MARKET_OU
    if is_main_first_half_goals_over_under(bet_name):
        return MARKET_OU_FH
    norm = normalize_api_football_market(bet_name, [])
    if norm in (MARKET_1X2, MARKET_DC, MARKET_OU, MARKET_OU_FH):
        return norm
    return None


def _normalize_selection(
    bet_name: str,
    bet_id: Any,
    raw_value: str,
    *,
    home_team_name: str | None,
    away_team_name: str | None,
) -> str | None:
    if is_strict_match_winner_market(bet_name, bet_id):
        sk = normalize_match_winner_selection(raw_value, home_team_name, away_team_name)
        return None if sk == "UNKNOWN" else sk
    if is_strict_double_chance_market(bet_name):
        sk = normalize_double_chance_selection(raw_value)
        return None if sk == "UNKNOWN" else sk
    if is_main_full_time_goals_over_under(bet_name, bet_id):
        return normalize_over_under_selection(raw_value)
    if is_main_first_half_goals_over_under(bet_name):
        return normalize_first_half_over_under_selection(raw_value)
    return None


def parse_all_betfair_markets(
    raw_items: list[dict[str, Any]],
    *,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parsa tutti i mercati Betfair dal payload raw API."""
    markets_out: list[dict[str, Any]] = []
    raw_payload_bets: list[dict[str, Any]] = []

    for item in raw_items:
        for bm in item.get("bookmakers") or []:
            if not isinstance(bm, dict):
                continue
            bid = bm.get("id")
            if bid is not None and int(bid) != _BETFAIR_ID:
                continue
            for bet in bm.get("bets") or []:
                if not isinstance(bet, dict):
                    continue
                bet_name = str(bet.get("name") or "")
                bet_id = bet.get("id")
                norm_mkt = _normalize_market_label(bet_name, bet_id)
                values_out: list[dict[str, Any]] = []
                for val in bet.get("values") or []:
                    if not isinstance(val, dict):
                        continue
                    raw_value = str(val.get("value") or "")
                    odd = val.get("odd")
                    norm_sel = _normalize_selection(
                        bet_name,
                        bet_id,
                        raw_value,
                        home_team_name=home_team_name,
                        away_team_name=away_team_name,
                    )
                    values_out.append(
                        {
                            "raw_value": raw_value,
                            "normalized_selection": norm_sel,
                            "odd": str(odd) if odd is not None else None,
                        },
                    )
                market_entry = {
                    "raw_market_name": bet_name,
                    "bet_id": bet_id,
                    "normalized_market": norm_mkt,
                    "values": values_out,
                }
                markets_out.append(market_entry)
                raw_payload_bets.append(
                    {
                        "name": bet_name,
                        "id": bet_id,
                        "values": bet.get("values"),
                    },
                )

    raw_payload = {
        "filtered_to_betfair_only": True,
        "bookmaker_id": _BETFAIR_ID,
        "payload": raw_items,
        "bets_summary": raw_payload_bets,
    }
    return markets_out, raw_payload
