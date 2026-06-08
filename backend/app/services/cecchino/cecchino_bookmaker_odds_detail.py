"""Dettaglio quote Betfair stabile per Cecchino Today (13 righe fisse)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS, KPI_V2_VERSION
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)


def _source_for_row(kpi_row: dict[str, Any] | None) -> str:
    if not kpi_row:
        return "not_available"
    src = kpi_row.get("book_source")
    if src in ("derived_from_1x2", "derived_from_betfair_1x2"):
        return "derived_from_1x2"
    if src in ("raw_betfair", "betfair", "cached_betfair_odds"):
        return "raw_betfair"
    if kpi_row.get("quota_book") is not None:
        return "raw_betfair"
    return "not_available"


def _placeholder_row(market_key: str, label: str) -> dict[str, Any]:
    return {
        "market_key": market_key,
        "label": label,
        "quota_betfair": None,
        "source": "not_available",
        "status": "not_available",
    }


def _row_from_kpi(kpi_row: dict[str, Any]) -> dict[str, Any]:
    quota = kpi_row.get("quota_book")
    status = kpi_row.get("status") or "not_available"
    if quota is not None and status == "book_only":
        status = "available"
    return {
        "market_key": kpi_row.get("market_key") or "",
        "label": kpi_row.get("segno") or kpi_row.get("label") or "",
        "quota_betfair": quota,
        "source": _source_for_row(kpi_row),
        "status": status,
    }


def build_bookmaker_odds_detail(kpi_panel: dict[str, Any] | None) -> dict[str, Any]:
    """Costruisce 13 righe Betfair-only da kpi_panel v2 (con placeholder se mancanti)."""
    version = (kpi_panel or {}).get("version")
    by_key: dict[str, dict[str, Any]] = {}
    for row in (kpi_panel or {}).get("rows") or []:
        if isinstance(row, dict) and row.get("market_key"):
            by_key[str(row["market_key"])] = row

    if version != KPI_V2_VERSION:
        for market_key, label in KPI_V2_ROW_DEFS:
            src = by_key.get(market_key)
            if src and src.get("bookmakers"):
                bm = src.get("bookmakers") or {}
                quota = bm.get("Betfair")
                by_key[market_key] = {
                    "market_key": market_key,
                    "segno": label,
                    "quota_book": quota,
                    "book_source": "raw_betfair" if quota is not None else "not_available",
                    "status": "available" if quota is not None else "not_available",
                }

    rows: list[dict[str, Any]] = []
    for market_key, label in KPI_V2_ROW_DEFS:
        src = by_key.get(market_key)
        if src:
            rows.append(_row_from_kpi(src))
        else:
            rows.append(_placeholder_row(market_key, label))

    return {"rows": rows}
