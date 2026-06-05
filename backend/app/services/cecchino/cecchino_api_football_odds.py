"""Parse quote API-Football per Cecchino."""

from __future__ import annotations

import re
from typing import Any

from app.services.bookmakers.bookmaker_constants import (
    MARKET_BTTS,
    MARKET_DOUBLE_CHANCE,
    MARKET_MATCH_WINNER_1X2,
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

_1X2_VALUE_MAP = {
    "home": SEL_HOME,
    "1": SEL_HOME,
    "draw": SEL_DRAW,
    "x": SEL_DRAW,
    "away": SEL_AWAY,
    "2": SEL_AWAY,
}

_DC_VALUE_MAP = {
    "home/draw": SEL_ONE_X,
    "1x": SEL_ONE_X,
    "home or draw": SEL_ONE_X,
    "draw/away": SEL_X_TWO,
    "x2": SEL_X_TWO,
    "draw or away": SEL_X_TWO,
    "home/away": SEL_ONE_TWO,
    "12": SEL_ONE_TWO,
    "home or away": SEL_ONE_TWO,
}


def _norm_val(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _parse_odd(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        v = float(str(raw).replace(",", "."))
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _map_1x2_value(value: str) -> str | None:
    return _1X2_VALUE_MAP.get(_norm_val(value))


def _map_dc_value(value: str) -> str | None:
    return _DC_VALUE_MAP.get(_norm_val(value))


def _map_ou_value(value: str) -> str | None:
    sk = normalize_over_under_selection(value)
    if sk in (SEL_OVER_1_5, SEL_OVER_2_5):
        return sk
    return None


def _map_ou_pt_value(value: str) -> str | None:
    sk = normalize_first_half_over_under_selection(value)
    if sk in (SEL_OVER_PT_0_5, SEL_OVER_PT_1_5):
        return sk
    return None


def parse_api_football_odds_response(
    response_items: list[dict[str, Any]],
    *,
    requested_markets: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Estrae righe {normalized_market, selection_key, selection_label, odds_value, market_label}.
    Ritorna (rows, missing_markets).
    """
    wanted = set(requested_markets or [MARKET_1X2, MARKET_DC, MARKET_OU, MARKET_OU_FH])
    rows: list[dict[str, Any]] = []
    found_markets: set[str] = set()

    for item in response_items:
        for bm in item.get("bookmakers") or []:
            if not isinstance(bm, dict):
                continue
            for bet in bm.get("bets") or []:
                if not isinstance(bet, dict):
                    continue
                bet_name = str(bet.get("name") or "")
                bet_id = bet.get("id")
                raw_value_labels = [
                    str(v.get("value") or "")
                    for v in (bet.get("values") or [])
                    if isinstance(v, dict)
                ]

                is_ft_ou = is_main_full_time_goals_over_under(bet_name, bet_id)
                is_fh_ou = is_main_first_half_goals_over_under(bet_name)

                if is_ft_ou or is_fh_ou:
                    norm_out = MARKET_OU if is_ft_ou else MARKET_OU_FH
                    market_label = MAIN_FT_OU_RAW_NAME if is_ft_ou else bet_name
                    if norm_out not in wanted:
                        continue
                    for val in bet.get("values") or []:
                        if not isinstance(val, dict):
                            continue
                        label = str(val.get("value") or "")
                        odd = _parse_odd(val.get("odd"))
                        if odd is None:
                            continue
                        sk = _map_ou_value(label) if is_ft_ou else _map_ou_pt_value(label)
                        if sk is None:
                            continue
                        found_markets.add(norm_out)
                        rows.append(
                            {
                                "normalized_market": norm_out,
                                "selection_key": sk,
                                "selection_label": label,
                                "odds_value": odd,
                                "market_label": market_label,
                                "provider_market_id": str(bet.get("id") or ""),
                                "raw_payload_json": {
                                    "bet_id": bet.get("id"),
                                    "bet_name": bet_name,
                                    "value": label,
                                    "odd": val.get("odd"),
                                    "normalized_selection": sk,
                                },
                            },
                        )
                    continue

                norm = normalize_api_football_market(bet_name, raw_value_labels)
                if norm not in wanted and norm not in (
                    MARKET_MATCH_WINNER_1X2,
                    MARKET_DOUBLE_CHANCE,
                    MARKET_BTTS,
                ):
                    continue
                if norm == MARKET_BTTS:
                    continue

                for val in bet.get("values") or []:
                    if not isinstance(val, dict):
                        continue
                    label = str(val.get("value") or "")
                    odd = _parse_odd(val.get("odd"))
                    if odd is None:
                        continue
                    sk: str | None = None
                    if norm == MARKET_MATCH_WINNER_1X2 or norm == MARKET_1X2:
                        sk = _map_1x2_value(label)
                        norm_out = MARKET_1X2
                    elif norm == MARKET_DOUBLE_CHANCE or norm == MARKET_DC:
                        sk = _map_dc_value(label)
                        norm_out = MARKET_DC
                    else:
                        continue
                    if sk is None:
                        continue
                    found_markets.add(norm_out)
                    rows.append(
                        {
                            "normalized_market": norm_out,
                            "selection_key": sk,
                            "selection_label": label,
                            "odds_value": odd,
                            "market_label": bet_name,
                            "provider_market_id": str(bet.get("id") or ""),
                            "raw_payload_json": {
                                "bet_id": bet.get("id"),
                                "bet_name": bet_name,
                                "value": label,
                                "odd": val.get("odd"),
                            },
                        },
                    )

    missing = sorted(wanted - found_markets)
    return rows, missing
