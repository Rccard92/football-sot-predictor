"""Dettaglio quote bookmaker stabile per Cecchino Today (8 righe fisse)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_bookmaker_derive import arithmetic_mean
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_X_TWO,
)

BOOK_NAMES = ("Bet365", "Betfair", "Pinnacle")

BOOKMAKER_ODDS_DETAIL_KEYS: tuple[tuple[str, str], ...] = (
    (SEL_HOME, "1"),
    (SEL_DRAW, "X"),
    (SEL_AWAY, "2"),
    (SEL_ONE_X, "1X"),
    (SEL_X_TWO, "X2"),
    (SEL_ONE_TWO, "12"),
    (SEL_OVER_1_5, "OVER 1.5"),
    (SEL_OVER_2_5, "OVER 2.5"),
)


def _empty_bookmakers() -> dict[str, float | None]:
    return {name: None for name in BOOK_NAMES}


def _normalize_bookmakers(raw: Any) -> dict[str, float | None]:
    out = _empty_bookmakers()
    if not isinstance(raw, dict):
        return out
    for name in BOOK_NAMES:
        val = raw.get(name)
        if val is not None:
            try:
                out[name] = float(val)
            except (TypeError, ValueError):
                out[name] = None
    return out


def _derive_average(bookmakers: dict[str, float | None]) -> float | None:
    present = [v for v in bookmakers.values() if v is not None]
    return arithmetic_mean(present) if present else None


def _derive_status(bookmakers: dict[str, float | None], fallback: str | None) -> str:
    present = sum(1 for v in bookmakers.values() if v is not None)
    if present == 0:
        return "not_available"
    if present < len(BOOK_NAMES):
        return "partial"
    return fallback if fallback in ("available", "partial", "not_available") else "available"


def _placeholder_row(market_key: str, label: str) -> dict[str, Any]:
    bm = _empty_bookmakers()
    return {
        "market_key": market_key,
        "label": label,
        "bookmakers": bm,
        "book_average": None,
        "status": "not_available",
    }


def _row_from_kpi(kpi_row: dict[str, Any]) -> dict[str, Any]:
    bm = _normalize_bookmakers(kpi_row.get("bookmakers"))
    avg = _derive_average(bm)
    status = _derive_status(bm, kpi_row.get("status"))
    return {
        "market_key": kpi_row.get("market_key") or "",
        "label": kpi_row.get("label") or "",
        "bookmakers": bm,
        "book_average": avg,
        "status": status,
    }


def build_bookmaker_odds_detail(kpi_panel: dict[str, Any] | None) -> dict[str, Any]:
    """Costruisce 8 righe bookmaker stabili da kpi_panel (con placeholder se mancanti)."""
    by_key: dict[str, dict[str, Any]] = {}
    for row in (kpi_panel or {}).get("rows") or []:
        if isinstance(row, dict) and row.get("market_key"):
            by_key[str(row["market_key"])] = row

    rows: list[dict[str, Any]] = []
    for market_key, label in BOOKMAKER_ODDS_DETAIL_KEYS:
        src = by_key.get(market_key)
        if src:
            rows.append(_row_from_kpi(src))
        else:
            rows.append(_placeholder_row(market_key, label))

    return {"rows": rows}
