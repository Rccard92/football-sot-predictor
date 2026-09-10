"""Gate provenienza quote RUN V2 — O/U REAL only, DC real-or-derived.

Non modifica formule V1. Valida e allinea i flag STRICT/KPI rispetto al
contratto Bet365 della RUN V2.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_0_5,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_0_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    FAMILY_DC,
    FAMILY_OU,
)

# Stesso valore di `quotes.ENRICHMENT_QUOTE_SOURCE` (evita import circolare).
ENRICHMENT_QUOTE_SOURCE = "bet365_enrichment_closing_pre_kickoff"

OU_REAL_ONLY_KEYS: tuple[str, ...] = (
    SEL_OVER_0_5,
    SEL_UNDER_0_5,
    SEL_OVER_1_5,
    SEL_UNDER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_3_5,
)

OU_SOURCE_COLUMN_BY_KEY: dict[str, str] = {
    SEL_OVER_0_5: "bet365_over_05",
    SEL_UNDER_0_5: "bet365_under_05",
    SEL_OVER_1_5: "bet365_over_15",
    SEL_UNDER_1_5: "bet365_under_15",
    SEL_OVER_2_5: "bet365_over_25",
    SEL_UNDER_2_5: "bet365_under_25",
    SEL_OVER_3_5: "bet365_over_35",
    SEL_UNDER_3_5: "bet365_under_35",
}

DC_KEYS: tuple[str, ...] = (SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO)


class QuoteProvenanceError(ValueError):
    """O/U presente marcato derived o disallineato dal contratto REAL."""

    def __init__(self, message: str, *, violations: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.violations = list(violations or [])


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 1.0 else None


def enforce_ou_real_only(
    strict_by_market: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """FAIL/STOP se un O/U con quota presente e marcato derived."""
    violations: list[dict[str, Any]] = []
    for mk in OU_REAL_ONLY_KEYS:
        entry = strict_by_market.get(mk) or {}
        value = _as_float(entry.get("value"))
        if value is None:
            continue
        if entry.get("is_derived") or entry.get("is_derived_quote"):
            violations.append(
                {
                    "market_key": mk,
                    "reason": "ou_present_marked_derived",
                    "source_column": entry.get("source_column"),
                    "value": value,
                }
            )
        if entry.get("is_real_quote") is False:
            violations.append(
                {
                    "market_key": mk,
                    "reason": "ou_present_not_real",
                    "source_column": entry.get("source_column"),
                    "value": value,
                }
            )
    if violations:
        raise QuoteProvenanceError(
            "Quote O/U presenti marcate derived/non-real: FAIL/STOP",
            violations=violations,
        )
    return []


def align_strict_quote_provenance(
    strict_by_market: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Allinea flag STRICT al contratto RUN V2 (muta e restituisce la mappa)."""
    out = strict_by_market
    for market in CORE_MARKETS:
        entry = out.get(market.key)
        if not isinstance(entry, dict):
            continue
        value = _as_float(entry.get("value"))
        expected_col = (
            market.strict_quote_columns[0] if market.strict_quote_columns else None
        )

        if market.family == FAMILY_OU and value is not None:
            entry["is_real_quote"] = True
            entry["is_derived"] = False
            entry["derivation_method"] = None
            entry["pre_match_input_safe"] = True
            entry["used_for_prediction"] = True
            entry["used_for_prediction_pipeline"] = True
            entry["economic_observation_only"] = False
            entry["available_at_prediction_time"] = True
            entry["market_quote_available"] = True
            if expected_col:
                entry["source_column"] = expected_col
            if not entry.get("quote_source"):
                entry["quote_source"] = ENRICHMENT_QUOTE_SOURCE
            out[market.key] = entry
            continue

        if market.family == FAMILY_DC and value is not None:
            if entry.get("is_derived"):
                entry["is_real_quote"] = False
                entry["used_for_prediction"] = True
                entry["pre_match_input_safe"] = True
                entry["economic_observation_only"] = False
            else:
                entry["is_real_quote"] = True
                entry["is_derived"] = False
                entry["derivation_method"] = None
                entry["used_for_prediction"] = True
                entry["pre_match_input_safe"] = True
                entry["economic_observation_only"] = False
                if expected_col:
                    entry["source_column"] = expected_col
                if not entry.get("quote_source") or "derived" in str(
                    entry.get("quote_source") or ""
                ).lower():
                    entry["quote_source"] = ENRICHMENT_QUOTE_SOURCE
            out[market.key] = entry

    enforce_ou_real_only(out)
    return out


def sync_kpi_rows_to_strict(
    panel: dict[str, Any],
    *,
    strict_by_market: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Forza KPI.quota_book = STRICT Bet365 per O/U e DC reale; allinea book_source."""
    out = dict(panel)
    rows: list[dict[str, Any]] = []
    for row in out.get("rows") or []:
        if not isinstance(row, dict):
            continue
        r = dict(row)
        mk = str(r.get("market_key") or "")
        q = strict_by_market.get(mk) or {}
        strict_val = _as_float(q.get("value"))

        if mk in OU_REAL_ONLY_KEYS and strict_val is not None:
            if q.get("is_derived"):
                raise QuoteProvenanceError(
                    f"O/U {mk} STRICT derived durante sync KPI",
                    violations=[{"market_key": mk, "reason": "ou_derived_in_kpi_sync"}],
                )
            r["quota_book"] = round(strict_val, 3)
            r["book_source"] = str(q.get("quote_source") or ENRICHMENT_QUOTE_SOURCE)
            r["book_quote_class"] = "real_bet365"
            r["derived_quote"] = False
            r["not_real_book_quote"] = False
            r["force_derived_quote"] = False
            r["source_column"] = q.get("source_column") or OU_SOURCE_COLUMN_BY_KEY.get(mk)
            r["status"] = r.get("status") or "available"
        elif mk in DC_KEYS and strict_val is not None and not q.get("is_derived"):
            r["quota_book"] = round(strict_val, 3)
            r["book_source"] = str(q.get("quote_source") or ENRICHMENT_QUOTE_SOURCE)
            r["book_quote_class"] = "real_bet365"
            r["derived_quote"] = False
            r["not_real_book_quote"] = False
            r["force_derived_quote"] = False
            r["real_dc_quote"] = True
            r["status"] = r.get("status") or "available"
        rows.append(r)
    out["rows"] = rows
    out["run_v2_quote_provenance_synced"] = True
    return out


def build_market_provenance_matrix(
    *,
    strict_by_market: dict[str, dict[str, Any]],
    kpi_panel: dict[str, Any] | None = None,
    purchasability: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Matrice audit 17 mercati per report finale / test."""
    kpi_by = {
        str(r.get("market_key")): r
        for r in ((kpi_panel or {}).get("rows") or [])
        if isinstance(r, dict) and r.get("market_key")
    }
    purch_by = {
        str(m.get("market_key")): m
        for m in ((purchasability or {}).get("markets") or [])
        if isinstance(m, dict) and m.get("market_key")
    }
    rows: list[dict[str, Any]] = []
    for market in CORE_MARKETS:
        q = strict_by_market.get(market.key) or {}
        kpi = kpi_by.get(market.key) or {}
        purch = purch_by.get(market.key) or {}
        value = _as_float(q.get("value"))
        if value is None:
            kind = "missing"
        elif q.get("is_derived"):
            kind = "derived"
        elif q.get("is_real_quote"):
            kind = "real"
        else:
            kind = "unknown"
        expected_col = (
            market.strict_quote_columns[0] if market.strict_quote_columns else None
        )
        rows.append(
            {
                "market_key": market.key,
                "source_column": q.get("source_column") or expected_col,
                "real_or_derived": kind,
                "kpi_quota_book": kpi.get("quota_book"),
                "strict_quota_book": value,
                "edge_pct": kpi.get("edge_pct"),
                "purchasability_status": purch.get("status"),
                "purchasability_score": purch.get("score"),
                "used_for_prediction": bool(q.get("used_for_prediction"))
                if value is not None
                else False,
            }
        )
    return rows
