"""Pannello KPI Cecchino (tab DASHBOARD Excel)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_bookmaker_derive import arithmetic_mean
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS, CECCHINO_VERSION
from app.services.cecchino.cecchino_match_balance import classify_match_balance
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_DC,
    MARKET_OU,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_X_TWO,
)

DELTA_FORCE_LEGEND = [
    {"range": "< 15%", "label": "PARTITA STATISTICA (LINEARE)"},
    {"range": "16% - 34%", "label": "PARTITA NON STATISTICA"},
    {"range": "> 35%", "label": "> FORTE FAVORITA (NON LINEARE)"},
]


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, str):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _kpi_average(*values: Any) -> float | None:
    nums = [_num(v) for v in values]
    nums = [n for n in nums if n is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _edge(book: float | None, cecchino: float | None) -> float | None:
    b, c = _num(book), _num(cecchino)
    if b is None or c is None or c <= 0:
        return None
    return round((b / c - 1.0) * 100.0, 2)


def _prob_from_odd(odd: float | None) -> float | None:
    o = _num(odd)
    if o is None or o <= 0:
        return None
    return 1.0 / o


def _row(
    *,
    market_key: str,
    label: str,
    statistica: Any = None,
    cecchino: Any = None,
    book: Any = None,
    bookmakers: dict[str, Any] | None = None,
    book_average: Any = None,
    status: str = "available",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    media = _kpi_average(statistica, cecchino, book)
    edge = _edge(book, cecchino)
    return {
        "market_key": market_key,
        "label": label,
        "statistica": statistica,
        "cecchino": cecchino,
        "book": book,
        "bookmakers": bookmakers or {},
        "book_average": book_average,
        "media": media,
        "edge": edge,
        "edge_pct": edge,
        "status": status,
        "warnings": list(warnings or []),
    }


def build_cecchino_kpi_panel(
    *,
    statistical: dict[str, Any],
    final_odds: dict[str, Any],
    bookmaker_payload: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = list(bookmaker_payload.get("warnings") or [])
    bm_status = bookmaker_payload.get("status") or "not_available"
    avg = bookmaker_payload.get("bookmaker_average") or {}
    avg_1x2 = avg.get(MARKET_1X2) or {}
    avg_dc = avg.get("DOUBLE_CHANCE") or {}
    avg_ou = avg.get(MARKET_OU) or avg.get("OVER_UNDER_GOALS") or {}

    bookmakers_by_name: dict[str, dict[str, Any]] = {}
    for bm in bookmaker_payload.get("bookmakers") or []:
        if isinstance(bm, dict):
            bookmakers_by_name[bm.get("bookmaker_name", "")] = bm

    def _bm_vals(mkt: str, sk: str) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for name in ("Bet365", "Betfair", "Pinnacle"):
            bm = bookmakers_by_name.get(name) or {}
            if bm.get("status") != "available":
                out[name] = None
                continue
            out[name] = (bm.get("markets") or {}).get(mkt, {}).get(sk)
        return out

    stat_ok = statistical.get("status") == "available"
    cec_ok = final_odds.get("status") == "available"
    q1 = _num(final_odds.get("quota_1"))
    qx = _num(final_odds.get("quota_x"))
    q2 = _num(final_odds.get("quota_2"))
    p1 = _num(final_odds.get("prob_1"))
    px = _num(final_odds.get("prob_x"))
    p2 = _num(final_odds.get("prob_2"))

    cec_1x = round(100.0 / (p1 + px), 2) if p1 and px and (p1 + px) > 0 else None
    cec_x2 = round(100.0 / (px + p2), 2) if px and p2 and (px + p2) > 0 else None
    cec_12 = round(100.0 / (p1 + p2), 2) if p1 and p2 and (p1 + p2) > 0 else None

    book_home = avg_1x2.get(SEL_HOME)
    book_draw = avg_1x2.get(SEL_DRAW)
    book_away = avg_1x2.get(SEL_AWAY)
    book_1x = avg_dc.get(SEL_ONE_X)
    book_x2 = avg_dc.get(SEL_X_TWO)
    book_12 = avg_dc.get(SEL_ONE_TWO)

    bp1 = _prob_from_odd(book_home)
    bpx = _prob_from_odd(book_draw)
    bp2 = _prob_from_odd(book_away)
    book_delta = abs(bp1 - bp2) * 100 if bp1 is not None and bp2 is not None else None
    cec_delta = abs(p1 - p2) * 100 if p1 is not None and p2 is not None else None
    stat_delta = statistical.get("delta_forza")

    row_status = "available" if bm_status == "available" else ("partial" if bm_status == "partial" else "not_available")

    rows = [
        _row(
            market_key=SEL_HOME,
            label="1",
            statistica=statistical.get("odd_1") if stat_ok else None,
            cecchino=q1 if cec_ok else None,
            book=book_home,
            bookmakers=_bm_vals(MARKET_1X2, SEL_HOME),
            book_average=book_home,
            status=row_status,
        ),
        _row(
            market_key=SEL_DRAW,
            label="X",
            statistica=statistical.get("odd_x") if stat_ok else None,
            cecchino=qx if cec_ok else None,
            book=book_draw,
            bookmakers=_bm_vals(MARKET_1X2, SEL_DRAW),
            book_average=book_draw,
            status=row_status,
        ),
        _row(
            market_key=SEL_AWAY,
            label="2",
            statistica=statistical.get("odd_2") if stat_ok else None,
            cecchino=q2 if cec_ok else None,
            book=book_away,
            bookmakers=_bm_vals(MARKET_1X2, SEL_AWAY),
            book_average=book_away,
            status=row_status,
        ),
        _row(
            market_key=SEL_ONE_X,
            label="1X",
            statistica=statistical.get("odd_1x") if stat_ok else None,
            cecchino=cec_1x,
            book=book_1x,
            bookmakers=_bm_vals(MARKET_DC, SEL_ONE_X),
            book_average=book_1x,
            status=row_status,
        ),
        _row(
            market_key=SEL_X_TWO,
            label="X2",
            statistica=statistical.get("odd_x2") if stat_ok else None,
            cecchino=cec_x2,
            book=book_x2,
            bookmakers=_bm_vals(MARKET_DC, SEL_X_TWO),
            book_average=book_x2,
            status=row_status,
        ),
        _row(
            market_key=SEL_ONE_TWO,
            label="12",
            statistica=statistical.get("odd_12") if stat_ok else None,
            cecchino=cec_12,
            book=book_12,
            bookmakers=_bm_vals(MARKET_DC, SEL_ONE_TWO),
            book_average=book_12,
            status=row_status,
        ),
        _row(
            market_key=SEL_OVER_1_5,
            label="OVER 1.5",
            statistica=None,
            cecchino=None,
            book=avg_ou.get(SEL_OVER_1_5),
            book_average=avg_ou.get(SEL_OVER_1_5),
            status="not_available" if avg_ou.get(SEL_OVER_1_5) is None else row_status,
        ),
        _row(
            market_key=SEL_OVER_2_5,
            label="OVER 2.5",
            statistica=None,
            cecchino=None,
            book=avg_ou.get(SEL_OVER_2_5),
            book_average=avg_ou.get(SEL_OVER_2_5),
            status="not_available" if avg_ou.get(SEL_OVER_2_5) is None else row_status,
        ),
        _row(
            market_key="OVER_PT",
            label="OVER PT",
            statistica=None,
            cecchino=None,
            book=None,
            status="not_available",
        ),
        _row(
            market_key="MATCH_ANALYSIS",
            label="ANALISI DEL MATCH",
            statistica=statistical.get("match_analysis") if stat_ok else None,
            cecchino=classify_match_balance(p1, px, p2) if cec_ok else None,
            book=classify_match_balance(bp1, bpx, bp2) if bp1 else None,
            status=row_status,
        ),
        _row(
            market_key="DELTA_FORZA",
            label="DELTA DI FORZA",
            statistica=f"{stat_delta}%" if stat_delta is not None else None,
            cecchino=f"{round(cec_delta, 2)}%" if cec_delta is not None else None,
            book=f"{round(book_delta, 2)}%" if book_delta is not None else None,
            status=row_status,
        ),
    ]

    if bm_status == "not_available":
        warnings.append("Quote bookmaker non disponibili")

    bookmakers_used = [
        {
            "name": b["name"],
            "provider_bookmaker_id": int(b["provider_bookmaker_id"]),
            "status": next(
                (x.get("status", "missing") for x in (bookmaker_payload.get("bookmakers") or []) if x.get("bookmaker_name") == b["name"]),
                "missing",
            ),
        }
        for b in CECCHINO_BOOKMAKERS
    ]

    return {
        "version": CECCHINO_VERSION,
        "bookmakers_used": bookmakers_used,
        "bookmaker_status": bm_status,
        "rows": rows,
        "delta_force_legend": DELTA_FORCE_LEGEND,
        "warnings": warnings,
    }
