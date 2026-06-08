"""Mapping strict quote Betfair per KPI Cecchino Today."""

from __future__ import annotations

import re
from typing import Any

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
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

SEL_UNKNOWN = "UNKNOWN"

_SOURCE_MATCH_WINNER = "betfair_raw_match_winner"
_SOURCE_DOUBLE_CHANCE = "betfair_raw_double_chance"
_SOURCE_OVER_UNDER = "betfair_raw_over_under"
_SOURCE_OVER_UNDER_FH = "betfair_raw_over_under_first_half"
_SOURCE_DERIVED_DC = "derived_from_betfair_1x2"

_REJECT_1X2_PATTERNS = re.compile(
    r"(?:first|second|1st|2nd)\s*half|half\s*time|team\s*to\s*score\s*(?:first|last)|"
    r"to\s*qualify|winning\s*margin|correct\s*score",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _norm_team(s: str | None) -> str:
    if not s:
        return ""
    return _norm(re.sub(r"[^\w\s]", "", s))


def is_strict_match_winner_market(bet_name: str, bet_id: Any = None) -> bool:
    """Solo Match Winner full-time (bet_id=1 se presente)."""
    name = _norm(bet_name)
    if _REJECT_1X2_PATTERNS.search(bet_name):
        return False
    if name != "match winner":
        return False
    if bet_id is not None and str(bet_id) not in ("1", ""):
        try:
            if int(bet_id) != 1:
                return False
        except (TypeError, ValueError):
            return False
    return True


def is_strict_double_chance_market(bet_name: str) -> bool:
    return _norm(bet_name) == "double chance"


def normalize_match_winner_selection(
    raw_value: str,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> str:
    """Mappa selection Match Winner → HOME / DRAW / AWAY / UNKNOWN."""
    v = _norm(raw_value)
    if v in ("home", "1"):
        return SEL_HOME
    if v in ("draw", "x"):
        return SEL_DRAW
    if v in ("away", "2"):
        return SEL_AWAY
    home_n = _norm_team(home_team_name)
    away_n = _norm_team(away_team_name)
    rv = _norm_team(raw_value)
    if home_n and rv and (rv == home_n or home_n in rv or rv in home_n):
        return SEL_HOME
    if away_n and rv and (rv == away_n or away_n in rv or rv in away_n):
        return SEL_AWAY
    return SEL_UNKNOWN


def normalize_double_chance_selection(raw_value: str) -> str:
    v = _norm(raw_value)
    dc_map = {
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
    return dc_map.get(v, SEL_UNKNOWN)


def _source_priority(source: str) -> int:
    priorities = {
        _SOURCE_MATCH_WINNER: 10,
        _SOURCE_DOUBLE_CHANCE: 10,
        _SOURCE_OVER_UNDER: 10,
        _SOURCE_OVER_UNDER_FH: 10,
    }
    return priorities.get(source, 0)


def merge_parsed_row(
    by_mkt: dict[str, dict[str, dict[str, Any]]],
    row: dict[str, Any],
) -> None:
    """Aggrega righe parse preferendo source strict su duplicati."""
    mkt = row["normalized_market"]
    sk = row["selection_key"]
    prov = row.get("provenance") or {}
    source = prov.get("source") or ""
    existing = by_mkt.get(mkt, {}).get(sk)
    if existing is None:
        by_mkt.setdefault(mkt, {})[sk] = row
        return
    old_src = (existing.get("provenance") or {}).get("source") or ""
    if _source_priority(source) >= _source_priority(old_src):
        by_mkt[mkt][sk] = row


def parsed_rows_to_markets_and_provenance(
    parsed: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, Any]]]:
    by_mkt: dict[str, dict[str, dict[str, Any]]] = {}
    for pr in parsed:
        merge_parsed_row(by_mkt, pr)

    markets: dict[str, dict[str, float]] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for mkt, selections in by_mkt.items():
        markets[mkt] = {}
        for sk, row in selections.items():
            markets[mkt][sk] = float(row["odds_value"])
            provenance[sk] = dict(row.get("provenance") or {})
    return markets, provenance


def validate_betfair_kpi_odds_mapping(
    markets: dict[str, Any],
    provenance: dict[str, dict[str, Any]],
    dc_derived: dict[str, bool],
) -> list[str]:
    """Valida che ogni quota KPI abbia source tracciabile e mercato ammesso."""
    warnings: list[str] = []

    for sk in (SEL_HOME, SEL_DRAW, SEL_AWAY):
        if sk not in (markets.get(MARKET_1X2) or {}):
            continue
        prov = provenance.get(sk) or {}
        src = prov.get("source")
        if src != _SOURCE_MATCH_WINNER:
            warnings.append(f"1x2_{sk}:source_non_tracciabile:{src}")
        raw_mkt = prov.get("raw_market_name") or ""
        if raw_mkt and not is_strict_match_winner_market(raw_mkt, prov.get("bet_id")):
            warnings.append(f"1x2_{sk}:mercato_non_ammesso:{raw_mkt}")

    for sk in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
        dc = markets.get(MARKET_DC) or {}
        if sk not in dc:
            continue
        if dc_derived.get(sk):
            continue
        prov = provenance.get(sk) or {}
        src = prov.get("source")
        if src != _SOURCE_DOUBLE_CHANCE:
            warnings.append(f"dc_{sk}:source_non_tracciabile:{src}")

    for sk in (SEL_OVER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5, SEL_UNDER_3_5):
        if sk in (markets.get(MARKET_OU) or {}):
            prov = provenance.get(sk) or {}
            if prov.get("source") not in (_SOURCE_OVER_UNDER, None) and prov:
                warnings.append(f"ou_{sk}:source_sospetta:{prov.get('source')}")

    for sk in (SEL_UNDER_PT_1_5, SEL_OVER_PT_0_5, SEL_OVER_PT_1_5):
        if sk in (markets.get(MARKET_OU_FH) or {}):
            prov = provenance.get(sk) or {}
            if prov.get("source") not in (_SOURCE_OVER_UNDER_FH, None) and prov:
                warnings.append(f"ou_fh_{sk}:source_sospetta:{prov.get('source')}")

    return warnings
