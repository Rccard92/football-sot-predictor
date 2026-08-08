"""Mapping strict quote Betfair per KPI Cecchino Today."""

from __future__ import annotations

import re
from typing import Any

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

SEL_UNKNOWN = "UNKNOWN"

# Provenance sources (primary Betfair — legacy names preserved)
_SOURCE_MATCH_WINNER = "betfair_raw_match_winner"
_SOURCE_FH_MATCH_WINNER = "betfair_raw_first_half_match_winner"
_SOURCE_DOUBLE_CHANCE = "betfair_raw_double_chance"
_SOURCE_OVER_UNDER = "betfair_raw_over_under"
_SOURCE_OVER_UNDER_FH = "betfair_raw_over_under_first_half"
_SOURCE_DERIVED_DC = "derived_from_betfair_1x2"


def provenance_source_for(slug: str, kind: str) -> str:
    """kind: match_winner | fh_match_winner | double_chance | over_under | over_under_fh | derived_dc."""
    s = (slug or "betfair").strip().lower()
    mapping = {
        "match_winner": f"{s}_raw_match_winner",
        "fh_match_winner": f"{s}_raw_first_half_match_winner",
        "double_chance": f"{s}_raw_double_chance",
        "over_under": f"{s}_raw_over_under",
        "over_under_fh": f"{s}_raw_over_under_first_half",
        "derived_dc": f"derived_from_{s}_1x2",
    }
    return mapping[kind]


def is_raw_match_winner_source(src: str | None) -> bool:
    return bool(src) and str(src).endswith("_raw_match_winner")


def is_raw_fh_match_winner_source(src: str | None) -> bool:
    return bool(src) and str(src).endswith("_raw_first_half_match_winner")


def is_raw_double_chance_source(src: str | None) -> bool:
    return bool(src) and str(src).endswith("_raw_double_chance")


def is_raw_over_under_source(src: str | None) -> bool:
    return bool(src) and str(src).endswith("_raw_over_under")


def is_raw_over_under_fh_source(src: str | None) -> bool:
    return bool(src) and str(src).endswith("_raw_over_under_first_half")


def is_derived_dc_source(src: str | None) -> bool:
    return bool(src) and str(src).startswith("derived_from_") and str(src).endswith("_1x2")

_FH_1X2_ACCEPTED_NAMES = frozenset(
    {
        "first half winner",
        "1st half winner",
        "first half match winner",
        "half time result",
        "halftime result",
        "ht result",
        "1st half result",
    },
)

_REJECT_FH_1X2_EXTRA = re.compile(
    r"second\s*half|over\s*/\s*under|over/under|double\s*chance|correct\s*score|"
    r"both\s*teams\s*to\s*score|to\s*qualify|winning\s*margin|team\s*to\s*score",
    re.IGNORECASE,
)

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


def is_strict_first_half_match_winner_market(bet_name: str, bet_id: Any = None) -> bool:
    """Solo risultato 1X2 primo tempo — esclude FT winner, OU, DC, second half."""
    if _REJECT_FH_1X2_EXTRA.search(bet_name):
        return False
    name = _norm(bet_name)
    if name == "match winner":
        return False
    return name in _FH_1X2_ACCEPTED_NAMES


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


def normalize_first_half_match_winner_selection(
    raw_value: str,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> str:
    """Mappa selection FH 1X2 → HOME_PT / DRAW_PT / AWAY_PT / UNKNOWN."""
    v = _norm(raw_value)
    if v in ("home", "1"):
        return SEL_HOME_PT
    if v in ("draw", "x"):
        return SEL_DRAW_PT
    if v in ("away", "2"):
        return SEL_AWAY_PT
    home_n = _norm_team(home_team_name)
    away_n = _norm_team(away_team_name)
    rv = _norm_team(raw_value)
    if home_n and rv and (rv == home_n or home_n in rv or rv in home_n):
        return SEL_HOME_PT
    if away_n and rv and (rv == away_n or away_n in rv or rv in away_n):
        return SEL_AWAY_PT
    return SEL_UNKNOWN


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
    if (
        is_raw_match_winner_source(source)
        or is_raw_fh_match_winner_source(source)
        or is_raw_double_chance_source(source)
        or is_raw_over_under_source(source)
        or is_raw_over_under_fh_source(source)
    ):
        return 10
    return 0


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
        if not is_raw_match_winner_source(src):
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
        if not is_raw_double_chance_source(src):
            warnings.append(f"dc_{sk}:source_non_tracciabile:{src}")

    for sk in (
        SEL_OVER_1_5,
        SEL_UNDER_1_5,
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_3_5,
        SEL_UNDER_3_5,
    ):
        if sk in (markets.get(MARKET_OU) or {}):
            prov = provenance.get(sk) or {}
            src = prov.get("source")
            if src is not None and prov and not is_raw_over_under_source(src):
                warnings.append(f"ou_{sk}:source_sospetta:{src}")

    for sk in (
        SEL_UNDER_PT_0_5,
        SEL_UNDER_PT_1_5,
        SEL_OVER_PT_0_5,
        SEL_OVER_PT_1_5,
    ):
        if sk in (markets.get(MARKET_OU_FH) or {}):
            prov = provenance.get(sk) or {}
            src = prov.get("source")
            if src is not None and prov and not is_raw_over_under_fh_source(src):
                warnings.append(f"ou_fh_{sk}:source_sospetta:{src}")

    for sk in (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT):
        if sk not in (markets.get(MARKET_1X2_FH) or {}):
            continue
        prov = provenance.get(sk) or {}
        src = prov.get("source")
        if not is_raw_fh_match_winner_source(src):
            warnings.append(f"fh_1x2_{sk}:source_non_tracciabile:{src}")
        raw_mkt = prov.get("raw_market_name") or ""
        if raw_mkt and not is_strict_first_half_match_winner_market(raw_mkt, prov.get("bet_id")):
            warnings.append(f"fh_1x2_{sk}:mercato_non_ammesso:{raw_mkt}")

    return warnings
