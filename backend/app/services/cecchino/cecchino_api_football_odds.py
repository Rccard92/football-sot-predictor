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
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
)
from app.services.cecchino.cecchino_betfair_odds_mapping import (
    SEL_UNKNOWN,
    _SOURCE_DOUBLE_CHANCE,
    _SOURCE_MATCH_WINNER,
    _SOURCE_OVER_UNDER,
    _SOURCE_OVER_UNDER_FH,
    is_strict_double_chance_market,
    is_strict_match_winner_market,
    normalize_double_chance_selection,
    normalize_match_winner_selection,
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
    if sk in (SEL_OVER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5, SEL_UNDER_3_5):
        return sk
    return None


def _map_ou_pt_value(value: str) -> str | None:
    sk = normalize_first_half_over_under_selection(value)
    if sk in (SEL_OVER_PT_0_5, SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5):
        return sk
    return None


def parse_api_football_odds_response(
    response_items: list[dict[str, Any]],
    *,
    requested_markets: list[str] | None = None,
    strict_betfair_kpi: bool = False,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
    mapping_warnings: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Estrae righe {normalized_market, selection_key, selection_label, odds_value, market_label}.
    Ritorna (rows, missing_markets).
    """
    wanted = set(requested_markets or [MARKET_1X2, MARKET_DC, MARKET_OU, MARKET_OU_FH])
    rows: list[dict[str, Any]] = []
    found_markets: set[str] = set()
    warn = mapping_warnings if mapping_warnings is not None else []

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
                        ou_source = _SOURCE_OVER_UNDER if is_ft_ou else _SOURCE_OVER_UNDER_FH
                        row_data: dict[str, Any] = {
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
                        }
                        if strict_betfair_kpi:
                            row_data["provenance"] = {
                                "raw_market_name": bet_name,
                                "bet_id": bet.get("id"),
                                "raw_value": label,
                                "selection_key": sk,
                                "source": ou_source,
                            }
                        rows.append(row_data)
                    continue

                if strict_betfair_kpi:
                    is_1x2 = is_strict_match_winner_market(bet_name, bet_id)
                    is_dc = is_strict_double_chance_market(bet_name)
                    if not is_1x2 and not is_dc:
                        continue
                    if is_1x2 and MARKET_1X2 not in wanted:
                        continue
                    if is_dc and MARKET_DC not in wanted:
                        continue
                    for val in bet.get("values") or []:
                        if not isinstance(val, dict):
                            continue
                        label = str(val.get("value") or "")
                        odd = _parse_odd(val.get("odd"))
                        if odd is None:
                            continue
                        if is_1x2:
                            sk = normalize_match_winner_selection(
                                label,
                                home_team_name,
                                away_team_name,
                            )
                            if sk == SEL_UNKNOWN:
                                warn.append(f"1x2_selection_unknown:{label}")
                                continue
                            norm_out = MARKET_1X2
                            src = _SOURCE_MATCH_WINNER
                        else:
                            sk = normalize_double_chance_selection(label)
                            if sk == SEL_UNKNOWN:
                                warn.append(f"dc_selection_unknown:{label}")
                                continue
                            norm_out = MARKET_DC
                            src = _SOURCE_DOUBLE_CHANCE
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
                                "provenance": {
                                    "raw_market_name": bet_name,
                                    "bet_id": bet.get("id"),
                                    "raw_value": label,
                                    "selection_key": sk,
                                    "source": src,
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
