"""Append V2-only delle righe KPI OVER_0_5 / UNDER_0_5.

Riusa `_build_metrics_row` del modulo KPI V1 senza modificarlo.
`KPI_V2_ROW_DEFS` e `build_cecchino_kpi_panel_v2_betfair` restano invariati.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import _build_metrics_row
from app.services.cecchino.cecchino_selection_keys import SEL_OVER_0_5, SEL_UNDER_0_5

OU05_KPI_SEGNOS: dict[str, str] = {
    SEL_OVER_0_5: "Over 0.5",
    SEL_UNDER_0_5: "Under 0.5",
}

OU05_KPI_KEYS: tuple[str, ...] = (SEL_OVER_0_5, SEL_UNDER_0_5)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _quota_cecchino_from_ou05_block(block: dict[str, Any] | None) -> float | None:
    if not isinstance(block, dict):
        return None
    return _as_float(block.get("final_odd"))


def build_ou05_kpi_row(
    *,
    market_key: str,
    quota_book: float | None,
    quota_cecchino: float | None,
    book_source: str,
    cecchino_source: str | None = "goal_markets_ou_05_v2",
) -> dict[str, Any]:
    """Una riga KPI con le metriche V1 congelate (`_build_metrics_row`)."""
    segno = OU05_KPI_SEGNOS[market_key]
    row = _build_metrics_row(
        market_key=market_key,
        segno=segno,
        quota_book=quota_book,
        quota_cecchino=quota_cecchino,
        book_source=book_source if quota_book is not None else "not_available",
        cecchino_source=cecchino_source,
        bookmaker_name="Bet365",
        provider_bookmaker_id=0,
        book_fallback_used=False,
    )
    row["v2_only_kpi_row"] = True
    row["book_quote_class"] = (
        "real_bet365" if quota_book is not None else "unavailable"
    )
    return row


def append_ou05_kpi_rows(
    panel: dict[str, Any] | None,
    *,
    ou_05_markets: dict[str, Any] | None,
    strict_by_market: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Restituisce panel V1 + 2 righe OU 0.5, senza mutare le righe V1 esistenti."""
    base = dict(panel or {})
    v1_rows = [dict(r) for r in (base.get("rows") or []) if isinstance(r, dict)]
    # Idempotenza: rimuovi eventuali OU05 gia presenti prima di riappendere.
    v1_rows = [r for r in v1_rows if str(r.get("market_key")) not in OU05_KPI_SEGNOS]

    quotes = strict_by_market or {}
    blocks = ou_05_markets or {}
    extra: list[dict[str, Any]] = []
    for mk in OU05_KPI_KEYS:
        q = quotes.get(mk) or {}
        quota_book = _as_float(q.get("value"))
        quota_cecchino = _quota_cecchino_from_ou05_block(blocks.get(mk))
        book_source = str(q.get("quote_source") or "bet365_enrichment_closing_pre_kickoff")
        extra.append(
            build_ou05_kpi_row(
                market_key=mk,
                quota_book=quota_book,
                quota_cecchino=quota_cecchino,
                book_source=book_source,
            )
        )

    out = dict(base)
    out["rows"] = v1_rows + extra
    out["v2_ou05_kpi_extension"] = True
    out["v2_ou05_rows_added"] = len(extra)
    out["v1_row_count"] = len(v1_rows)
    return out
