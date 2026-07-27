"""Wrapper KPI storico Bet365 — riusa builder operativo senza modificarlo."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    KPI_V2_VERSION,
    build_cecchino_kpi_panel_v2_betfair,
)
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_KPI_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import (
    PROVIDER,
    PROVIDER_SOURCE,
    build_kpi_compatible_payload,
    build_match_quote_bundle,
)


def build_historical_kpi_panel_bet365(
    *,
    final_odds: dict[str, Any],
    match: Any,
    goal_markets: dict[str, Any] | None = None,
    quote_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Costruisce pannello KPI storico Bet365 con formule operative invarianti."""
    bundle = quote_bundle or build_match_quote_bundle(match)
    payload = build_kpi_compatible_payload(bundle)
    panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=final_odds,
        betfair_payload=payload,
        goal_markets=goal_markets,
    )

    # Riscrive esclusivamente i metadati provider (formule già calcolate).
    panel["version"] = HISTORICAL_KPI_VERSION
    panel["bookmaker"] = {
        "name": PROVIDER,
        "source": PROVIDER_SOURCE,
        "provider_bookmaker_id": 0,
        "provider_source": PROVIDER_SOURCE,
    }
    panel["historical_only"] = True
    panel["operational_today_unchanged"] = True
    panel["source_builder_version"] = KPI_V2_VERSION
    panel["quote_policy_version"] = HISTORICAL_QUOTE_POLICY_VERSION
    panel["quote_bundle_counts"] = bundle.get("counts")
    panel["kpi_1x2_real_available"] = bundle.get("kpi_1x2_real_available")
    panel["kpi_ou25_real_available"] = bundle.get("kpi_ou25_real_available")

    # Annota status riga per quote derivate/reali/mancanti
    quotes = bundle.get("quotes") or {}
    for row in panel.get("rows") or []:
        mk = row.get("market_key")
        q = quotes.get(mk) or {}
        if q.get("is_real_book_quote"):
            row["book_quote_class"] = "real_bet365"
            row["status"] = row.get("status") or "available"
        elif q.get("is_derived"):
            row["book_quote_class"] = "derived"
            if row.get("quota_book") is not None:
                row["status"] = "derived_book"
        elif row.get("quota_book") is None and row.get("quota_cecchino") is not None:
            row["book_quote_class"] = "unavailable"
            row["status"] = "model_only"
        elif row.get("quota_book") is None and row.get("quota_cecchino") is None:
            row["book_quote_class"] = "unavailable"
            row["status"] = "not_available"
        else:
            row["book_quote_class"] = "real_bet365"

    # Nessuna falsa provenienza Betfair nei metadati
    warnings = [w for w in (panel.get("warnings") or []) if "Betfair" not in str(w)]
    panel["warnings"] = warnings
    return panel
