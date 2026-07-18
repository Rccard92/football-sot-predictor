"""Fair Book probability — research Indice di Acquistabilità Fase 2A.4.

Dataset v1_1 invariato. Derivazione research-only (soprattutto DC da 1X2 normalizzato).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    FAMILY_MATCH_WINNER,
    FAMILY_OVER_UNDER,
    get_opposition,
    required_selections_for_normalization,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

SOURCE_1X2 = "normalized_1x2_market"
SOURCE_TWO_WAY = "normalized_two_way_market"
SOURCE_DC_DERIVED = "derived_double_chance_from_normalized_1x2"
SOURCE_RAW_SECONDARY = "raw_implied_secondary_only"

MATCH_WINNER_SELS = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
DC_SELS = frozenset({SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO})
PRIMARY_MARKETS = (
    SEL_HOME,
    SEL_DRAW,
    SEL_AWAY,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_PT_1_5,
)


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN/Inf
        return None
    return f


def _sel(row: dict[str, Any]) -> str:
    return str(row.get("raw_market_code") or row.get("selection") or "")


def _odds(row: dict[str, Any]) -> float | None:
    o = _num(row.get("odds"))
    if o is None or o <= 1.0:
        return None
    return o


def _snapshot(row: dict[str, Any]) -> str:
    return str(row.get("snapshot_at") or "")


def _bookmaker(row: dict[str, Any]) -> str:
    return str(row.get("bookmaker_name") or "")


def _odds_source(row: dict[str, Any]) -> str:
    return str(row.get("odds_source") or row.get("book_source") or "")


def sibling_match_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("today_fixture_id"),
        _snapshot(row),
        _bookmaker(row),
        _odds_source(row),
    )


def normalize_exclusive_market(
    odds_by_sel: dict[str, float],
    required: frozenset[str],
) -> tuple[dict[str, float] | None, float | None, str]:
    if not required.issubset(set(odds_by_sel.keys())):
        return None, None, "incomplete_market"
    implied = {k: 1.0 / odds_by_sel[k] for k in required if odds_by_sel[k] > 0}
    if len(implied) != len(required):
        return None, None, "incomplete_market"
    total = sum(implied.values())
    if total <= 0:
        return None, None, "invalid_implied_sum"
    overround = total - 1.0
    normalized = {k: implied[k] / total for k in implied}
    return normalized, overround, "ok"


def _raw_fallback(row: dict[str, Any], reason: str) -> dict[str, Any]:
    odds = _odds(row)
    raw = _num(row.get("raw_book_implied_probability"))
    if raw is None and odds and odds > 0:
        raw = 1.0 / odds
    return {
        "fair_book_probability": raw,
        "fair_book_probability_source": SOURCE_RAW_SECONDARY,
        "fair_book_probability_verified": False,
        "normalization_payload": {
            "status": "fallback_raw_implied",
            "exclusion_reason": reason,
        },
        "exclusion_reason": reason,
    }


def _verified(
    *,
    prob: float,
    source: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "fair_book_probability": float(prob),
        "fair_book_probability_source": source,
        "fair_book_probability_verified": True,
        "normalization_payload": payload,
        "exclusion_reason": None,
    }


def resolve_fair_book_probability(
    row: dict[str, Any],
    sibling_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Risolve probabilità Book equa verificabile per una riga dataset."""
    sel = _sel(row)
    if not sel:
        return _raw_fallback(row, "market_key_missing")

    opp = get_opposition(sel)
    family = opp.get("canonical_market_family")
    period = opp.get("period")
    line = opp.get("line")

    # Filter siblings: same fixture/snapshot/bookmaker/source; reject mismatches
    row_key = sibling_match_key(row)
    matched: list[dict[str, Any]] = []
    for s in sibling_rows:
        if sibling_match_key(s) != row_key:
            # explicit exclusion reasons for diagnostics
            if s.get("today_fixture_id") != row.get("today_fixture_id"):
                continue
            if _snapshot(s) != _snapshot(row):
                continue  # different snapshot
            if _bookmaker(s) != _bookmaker(row):
                continue  # different bookmaker
            if _odds_source(s) != _odds_source(row):
                continue
            continue
        matched.append(s)

    # Include self if missing from siblings
    if not any(_sel(s) == sel for s in matched):
        matched = list(matched) + [row]

    odds_by_sel: dict[str, float] = {}
    for s in matched:
        sk = _sel(s)
        o = _odds(s)
        if sk and o is not None:
            odds_by_sel[sk] = o

    # --- 1X2 ---
    if sel in MATCH_WINNER_SELS and family == FAMILY_MATCH_WINNER:
        required = required_selections_for_normalization(FAMILY_MATCH_WINNER, period, line)
        if not required:
            return _raw_fallback(row, "no_normalization_set")
        # only same family/period/line odds
        scoped = {
            k: v
            for k, v in odds_by_sel.items()
            if get_opposition(k).get("canonical_market_family") == FAMILY_MATCH_WINNER
            and get_opposition(k).get("period") == period
            and get_opposition(k).get("line") == line
        }
        normalized, overround, status = normalize_exclusive_market(scoped, required)
        if status != "ok" or not normalized or sel not in normalized:
            return _raw_fallback(row, status if status != "ok" else "selection_missing")
        return _verified(
            prob=normalized[sel],
            source=SOURCE_1X2,
            payload={
                "status": status,
                "overround": overround,
                "normalized_map": {k: round(v, 8) for k, v in normalized.items()},
                "required": sorted(required),
            },
        )

    # --- Over/Under two-way ---
    if family == FAMILY_OVER_UNDER and sel in (
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_PT_1_5,
        SEL_UNDER_PT_1_5,
    ):
        required = required_selections_for_normalization(FAMILY_OVER_UNDER, period, line)
        if not required:
            return _raw_fallback(row, "no_normalization_set")
        scoped = {
            k: v
            for k, v in odds_by_sel.items()
            if get_opposition(k).get("canonical_market_family") == FAMILY_OVER_UNDER
            and get_opposition(k).get("period") == period
            and get_opposition(k).get("line") == line
        }
        # Reject if sibling has different period/line mixed in required set check
        normalized, overround, status = normalize_exclusive_market(scoped, required)
        if status != "ok" or not normalized or sel not in normalized:
            return _raw_fallback(row, status if status != "ok" else "selection_missing")
        return _verified(
            prob=normalized[sel],
            source=SOURCE_TWO_WAY,
            payload={
                "status": status,
                "overround": overround,
                "period": period,
                "line": line,
                "normalized_map": {k: round(v, 8) for k, v in normalized.items()},
                "required": sorted(required),
            },
        )

    # --- Double chance derived from normalized 1X2 ---
    if sel in DC_SELS or family == FAMILY_DOUBLE_CHANCE:
        # Cross-family: use match_winner siblings only
        mw_odds = {
            k: v
            for k, v in odds_by_sel.items()
            if k in MATCH_WINNER_SELS
            and get_opposition(k).get("canonical_market_family") == FAMILY_MATCH_WINNER
            and get_opposition(k).get("period") == period
        }
        # Also pull from sibling_rows that are match_winner even if family filter above
        for s in sibling_rows:
            if sibling_match_key(s) != row_key:
                continue
            sk = _sel(s)
            if sk not in MATCH_WINNER_SELS:
                continue
            o = _odds(s)
            if o is not None:
                mw_odds[sk] = o

        required = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY})
        normalized, overround, status = normalize_exclusive_market(mw_odds, required)
        if status != "ok" or not normalized:
            return _raw_fallback(row, f"dc_1x2_unavailable:{status}")

        p_h = normalized[SEL_HOME]
        p_d = normalized[SEL_DRAW]
        p_a = normalized[SEL_AWAY]
        derived = {
            SEL_ONE_X: p_h + p_d,
            SEL_X_TWO: p_d + p_a,
            SEL_ONE_TWO: p_h + p_a,
        }
        if sel not in derived:
            return _raw_fallback(row, "dc_selection_unknown")
        return _verified(
            prob=derived[sel],
            source=SOURCE_DC_DERIVED,
            payload={
                "status": "ok",
                "overround_1x2": overround,
                "normalized_1x2": {k: round(v, 8) for k, v in normalized.items()},
                "derived_dc": {k: round(v, 8) for k, v in derived.items()},
                "note": "DC not normalized as three-way exclusive market",
            },
        )

    return _raw_fallback(row, "unsupported_market_for_fair_book")


def build_sibling_index(rows: list[dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    """Index all rows by fixture+snapshot+bookmaker+source for fair resolution."""
    idx: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        idx[sibling_match_key(r)].append(r)
    return idx


def resolve_fair_for_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach fair book fields to each row (in-place copy list of enriched dicts)."""
    idx = build_sibling_index(rows)
    out: list[dict[str, Any]] = []
    for r in rows:
        siblings = idx.get(sibling_match_key(r), [r])
        fair = resolve_fair_book_probability(r, siblings)
        enriched = dict(r)
        enriched.update(fair)
        out.append(enriched)
    return out
