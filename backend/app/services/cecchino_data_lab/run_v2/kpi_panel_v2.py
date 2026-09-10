"""Pannello KPI RUN V2: V1 invariato + quote enrichment + OU 0.5 V2-only.

Non modifica `cecchino_kpi_panel_v2_betfair.py`. Alimenta input `quota_book`
gia previsti dal builder V1 (HT, DC, O/U 1.5/3.5) e appende OU 0.5.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    build_cecchino_kpi_panel_v2_betfair,
)
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2_FH,
    MARKET_DC,
    MARKET_OU,
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_3_5,
    SEL_UNDER_1_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_KPI_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import (
    PROVIDER,
    build_kpi_compatible_payload,
)
from app.services.cecchino_data_lab.run_v2.kpi_ou05_ext import append_ou05_kpi_rows
from app.services.cecchino_data_lab.run_v2.quotes import ENRICHMENT_QUOTE_SOURCE

_HT_KEYS = (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT)
_DC_KEYS = (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO)
_OU_EXT_KEYS = (SEL_OVER_1_5, SEL_UNDER_1_5, SEL_OVER_3_5, SEL_UNDER_3_5)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 1.0 else None


def _merge_enrichment_into_kpi_payload(
    payload: dict[str, Any],
    *,
    strict_by_market: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Inietta quote enrichment reali negli slot KPI V1 gia previsti."""
    out = deepcopy(payload)
    bookmakers = list(out.get("bookmakers") or [])
    if not bookmakers:
        bookmakers = [
            {
                "bookmaker_name": PROVIDER,
                "provider_bookmaker_id": 0,
                "status": "available",
                "markets": {},
                "dc_derived": {},
                "provenance_by_selection": {},
            }
        ]
        out["bookmakers"] = bookmakers

    bm = dict(bookmakers[0])
    markets = {k: dict(v) for k, v in (bm.get("markets") or {}).items()}
    provenance = dict(bm.get("provenance_by_selection") or {})
    dc_derived = dict(bm.get("dc_derived") or {})

    def _apply(market_bucket: str, market_key: str) -> None:
        q = strict_by_market.get(market_key) or {}
        value = _as_float(q.get("value"))
        if value is None or q.get("is_derived"):
            return
        bucket = dict(markets.get(market_bucket) or {})
        bucket[market_key] = value
        markets[market_bucket] = bucket
        provenance[market_key] = {
            "source": q.get("quote_source") or ENRICHMENT_QUOTE_SOURCE,
            "raw_market_name": f"Bet365 enrichment {market_key}",
            "selection_key": market_key,
            "bookmaker_name": PROVIDER,
            "provider_bookmaker_id": 0,
            "book_fallback_used": False,
            "source_column": q.get("source_column"),
            "temporal_classification": q.get("temporal_classification"),
        }

    for mk in _HT_KEYS:
        _apply(MARKET_1X2_FH, mk)
    for mk in _OU_EXT_KEYS:
        _apply(MARKET_OU, mk)

    # DC 1A: reale sostituisce la derivata; altrimenti resta il payload V1.
    dc_bucket = dict(markets.get(MARKET_DC) or {})
    for mk in _DC_KEYS:
        q = strict_by_market.get(mk) or {}
        value = _as_float(q.get("value"))
        if value is None:
            continue
        if q.get("is_derived"):
            # Mantieni eventuale derivata gia presente dal payload V1.
            continue
        dc_bucket[mk] = value
        dc_derived[mk] = False
        provenance[mk] = {
            "source": q.get("quote_source") or ENRICHMENT_QUOTE_SOURCE,
            "raw_market_name": f"Bet365 enrichment {mk}",
            "selection_key": mk,
            "bookmaker_name": PROVIDER,
            "provider_bookmaker_id": 0,
            "book_fallback_used": False,
            "source_column": q.get("source_column"),
            "temporal_classification": q.get("temporal_classification"),
            "real_dc_quote": True,
        }
    if dc_bucket:
        markets[MARKET_DC] = dc_bucket

    bm["markets"] = markets
    bm["dc_derived"] = dc_derived
    bm["provenance_by_selection"] = provenance
    bm["status"] = "available" if markets else bm.get("status")
    out["bookmakers"] = [bm]
    out["provenance_by_selection"] = provenance
    out["odds_source"] = out.get("odds_source") or "bet365_historical_csv"
    if markets and out.get("status") == "not_available":
        out["status"] = "partial"
    return out


def _annotate_book_quote_class(
    panel: dict[str, Any],
    *,
    strict_by_market: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    out = dict(panel)
    rows: list[dict[str, Any]] = []
    for row in out.get("rows") or []:
        if not isinstance(row, dict):
            continue
        r = dict(row)
        mk = str(r.get("market_key") or "")
        q = strict_by_market.get(mk) or {}
        if q.get("is_real_quote") and r.get("quota_book") is not None:
            r["book_quote_class"] = "real_bet365"
            r["status"] = r.get("status") or "available"
        elif q.get("is_derived") and r.get("quota_book") is not None:
            r["book_quote_class"] = "derived"
            r["status"] = "derived_book"
        elif r.get("quota_book") is None and r.get("quota_cecchino") is not None:
            r["book_quote_class"] = "unavailable"
            r["status"] = "model_only"
        rows.append(r)
    out["rows"] = rows
    return out


def build_run_v2_kpi_panel(
    *,
    final_odds: dict[str, Any],
    match: Any,
    goal_markets: dict[str, Any] | None,
    ou_05_markets: dict[str, Any] | None,
    ht_1x2_markets: dict[str, Any] | None = None,
    quote_bundle: dict[str, Any],
) -> dict[str, Any]:
    """KPI RUN V2 = panel V1 (formule invariate) + enrichment + OU05 append."""
    strict_v1 = quote_bundle.get("strict_v1_bundle") or {}
    strict_by_market = quote_bundle.get("strict_by_market") or {}

    base_payload = build_kpi_compatible_payload(strict_v1)
    payload = _merge_enrichment_into_kpi_payload(
        base_payload, strict_by_market=strict_by_market
    )

    # HT Cecchino: la V1-lab espone solo X PT in goal_markets; la famiglia
    # normalizzata V2 alimenta 1/X/2 PT senza modificare il builder KPI.
    merged_goal_markets = dict(goal_markets or {})
    for mk, block in (ht_1x2_markets or {}).items():
        if isinstance(block, dict) and block.get("final_odd") is not None:
            merged_goal_markets[mk] = block

    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=final_odds,
        betfair_payload=payload,
        goal_markets=merged_goal_markets,
    )
    panel["version"] = HISTORICAL_KPI_VERSION
    panel["bookmaker"] = {
        "name": PROVIDER,
        "source": quote_bundle.get("enrichment_provider_source")
        or strict_v1.get("provider_source"),
        "provider_bookmaker_id": 0,
        "provider_source": quote_bundle.get("enrichment_provider_source"),
    }
    panel["historical_only"] = True
    panel["operational_today_unchanged"] = True
    panel["quote_policy_version"] = (
        quote_bundle.get("quote_policy_version") or HISTORICAL_QUOTE_POLICY_VERSION_V4
    )
    panel["run_v2_enrichment_quotes_injected"] = True

    panel = _annotate_book_quote_class(panel, strict_by_market=strict_by_market)
    panel = append_ou05_kpi_rows(
        panel,
        ou_05_markets=ou_05_markets,
        strict_by_market=strict_by_market,
    )
    from app.services.cecchino_data_lab.run_v2.quote_provenance import (
        sync_kpi_rows_to_strict,
    )

    panel = sync_kpi_rows_to_strict(panel, strict_by_market=strict_by_market)
    # Silence unused match (parity con wrapper storico; utile a caller).
    _ = match
    return panel
