"""Deriva doppie chance e medie bookmaker da quote 1X2."""

from __future__ import annotations

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
    SEL_X_TWO,
)


def _prob_pct(odd: float) -> float:
    return 100.0 / float(odd)


def derive_double_chance_from_1x2(
    home: float | None,
    draw: float | None,
    away: float | None,
) -> dict[str, float | None]:
    if home is None or draw is None or away is None:
        return {"ONE_X": None, "X_TWO": None, "ONE_TWO": None}
    p1 = _prob_pct(home)
    px = _prob_pct(draw)
    p2 = _prob_pct(away)
    s1x = p1 + px
    sx2 = px + p2
    s12 = p1 + p2
    if s1x <= 0 or sx2 <= 0 or s12 <= 0:
        return {"ONE_X": None, "X_TWO": None, "ONE_TWO": None}
    return {
        "ONE_X": round(100.0 / s1x, 2),
        "X_TWO": round(100.0 / sx2, 2),
        "ONE_TWO": round(100.0 / s12, 2),
    }


def arithmetic_mean(values: list[float]) -> float | None:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def build_bookmaker_structures(
    rows: list[Any],
    *,
    bookmaker_defs: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float | None]], list[str], str]:
    """
    Da righe DB → per-book markets dict + bookmaker_average + warnings + status.
    """
    by_bm: dict[str, dict[str, dict[str, float]]] = {}
    for d in bookmaker_defs:
        by_bm[str(d["provider_bookmaker_id"])] = {}

    for row in rows:
        bid = str(row.provider_bookmaker_id)
        mkt = row.normalized_market
        sk = row.selection_key
        by_bm.setdefault(bid, {}).setdefault(mkt, {})[sk] = float(row.odds_value)

    warnings: list[str] = []
    bookmakers_out: list[dict[str, Any]] = []
    available_count = 0

    for d in bookmaker_defs:
        bid = str(d["provider_bookmaker_id"])
        name = d["name"]
        markets_raw = by_bm.get(bid, {})
        m1 = markets_raw.get(MARKET_1X2, {})
        home = m1.get(SEL_HOME)
        draw = m1.get(SEL_DRAW)
        away = m1.get(SEL_AWAY)
        derived = derive_double_chance_from_1x2(home, draw, away)
        if home is None or draw is None or away is None:
            if any(x is not None for x in (home, draw, away)):
                warnings.append(f"{name}: 1X2 incompleto, doppie chance non calcolate")
            status = "missing"
        else:
            status = "available"
            available_count += 1

        markets: dict[str, Any] = {}
        if status == "available":
            markets[MARKET_1X2] = {SEL_HOME: home, SEL_DRAW: draw, SEL_AWAY: away}
            dc = markets_raw.get(MARKET_DC, {})
            markets[MARKET_DC] = {
                SEL_ONE_X: dc.get(SEL_ONE_X) or derived.get("ONE_X"),
                SEL_X_TWO: dc.get(SEL_X_TWO) or derived.get("X_TWO"),
                SEL_ONE_TWO: dc.get(SEL_ONE_TWO) or derived.get("ONE_TWO"),
            }
            ou = markets_raw.get(MARKET_OU, {})
            if ou:
                markets[MARKET_OU] = dict(ou)
            ou_fh = markets_raw.get(MARKET_OU_FH, {})
            if ou_fh:
                markets[MARKET_OU_FH] = dict(ou_fh)

        bookmakers_out.append(
            {
                "bookmaker_name": name,
                "provider_bookmaker_id": int(bid) if bid.isdigit() else bid,
                "status": status,
                "markets": markets,
            },
        )

    avg: dict[str, dict[str, float | None]] = {}
    for mkt, keys in (
        (MARKET_1X2, [SEL_HOME, SEL_DRAW, SEL_AWAY]),
        (MARKET_DC, [SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO]),
        (MARKET_OU, [SEL_OVER_1_5, SEL_OVER_2_5]),
        (MARKET_OU_FH, [SEL_OVER_PT_0_5, SEL_OVER_PT_1_5]),
    ):
        avg[mkt] = {}
        for sk in keys:
            vals: list[float] = []
            for bm in bookmakers_out:
                if bm["status"] != "available":
                    continue
                v = (bm.get("markets") or {}).get(mkt, {}).get(sk)
                if v is not None:
                    vals.append(float(v))
            avg[mkt][sk] = arithmetic_mean(vals)

    if available_count == 0:
        overall = "not_available"
    elif available_count < len(bookmaker_defs):
        overall = "partial"
    else:
        overall = "available"

    return bookmakers_out, avg, warnings, overall
