"""Bundle quote RUN V2 — 17 mercati CORE STRICT pre-match.

Le 5 quote legacy Football-Data restano sul percorso adapter V1
(`bet365_pre_reference_v4`). Le 12 colonne enrichment (source field
`*_last_seen`) sono classificate closing/pre-kickoff e quindi STRICT:

- temporal_classification = closing_pre_kickoff
- pre_match_input_safe = true
- available_at_prediction_time = true
- used_for_prediction = true
- economic_observation_only = false

DC: quota reale Bet365 se disponibile; fallback alla derivata 1X2 solo se
la reale e assente. Nessuna nuova formula.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.cecchino_data_lab.constants import (
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_QUOTE_REFERENCE_TIMING,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import (
    build_match_quote_bundle,
)
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    ENRICHMENT_STRICT_QUOTE_COLUMNS,
    FAMILY_DC,
    FAMILY_HT_1X2,
    FAMILY_OU,
    QUOTE_SNAPSHOT_CLOSING_PRE_KICKOFF,
    QUOTE_SNAPSHOT_PRE_REFERENCE,
    RUN_V2_QUOTE_POLICY_VERSION,
    TEMPORAL_CLASSIFICATION_CLOSING_PRE_KICKOFF,
    MarketDef,
)

PROVIDER = "Bet365"
ENRICHMENT_QUOTE_SOURCE = "bet365_enrichment_closing_pre_kickoff"
ENRICHMENT_PROVIDER_SOURCE = (
    "Bet365 enrichment CSV (*_last_seen = closing/pre-kickoff)"
)


def _num(value: Any) -> float | None:
    """Quota valida o None. Nessuna correzione del valore letto."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 1.0:
        return None
    return f


def _enrichment_family_groups() -> dict[str, list[MarketDef]]:
    groups: dict[str, list[MarketDef]] = {}
    for m in CORE_MARKETS:
        cols = m.strict_quote_columns
        if not cols or cols[0] not in ENRICHMENT_STRICT_QUOTE_COLUMNS:
            continue
        if m.family == FAMILY_DC:
            key = "dc"
        elif m.family == FAMILY_HT_1X2:
            key = "ht_1x2"
        elif m.family == FAMILY_OU:
            key = f"ou_{(m.line or '').replace('.', '_')}"
        else:
            key = m.family.lower()
        groups.setdefault(key, []).append(m)
    return groups


def _apply_family_normalization(
    quotes: dict[str, dict[str, Any]],
) -> None:
    """Overround e fair probability sulle famiglie enrichment complete."""
    for fam_key, markets in _enrichment_family_groups().items():
        entries = [quotes[m.key] for m in markets if m.key in quotes]
        values = [e.get("value") for e in entries]
        complete = bool(entries) and all(v is not None for v in values)
        raw_sum = sum(1.0 / v for v in values if v) if complete else None

        normalizer = None
        if complete and raw_sum:
            normalizer = raw_sum / 2.0 if fam_key == "dc" else raw_sum

        for entry in entries:
            entry["family_complete"] = complete
            if not complete or not normalizer:
                continue
            raw = 1.0 / float(entry["value"])
            entry["prob_raw"] = round(raw, 6)
            entry["prob_fair"] = round(raw / normalizer, 6)
            entry["overround"] = round(raw_sum, 6) if raw_sum else None


def _enrichment_strict_entry(
    market: MarketDef,
    value: float | None,
) -> dict[str, Any]:
    col = market.strict_quote_columns[0] if market.strict_quote_columns else None
    present = value is not None
    return {
        "market_key": market.key,
        "export_key": market.export_key,
        "value": round(value, 3) if present else None,
        "quote_source": ENRICHMENT_QUOTE_SOURCE if present else None,
        "quote_type": "core_strict",
        "provider": PROVIDER,
        "source_column": col,
        "quote_snapshot_type": (
            QUOTE_SNAPSHOT_CLOSING_PRE_KICKOFF if present else None
        ),
        "temporal_classification": (
            TEMPORAL_CLASSIFICATION_CLOSING_PRE_KICKOFF if present else None
        ),
        "is_real_quote": present,
        "is_derived": False,
        "derivation_method": None,
        "market_quote_available": present,
        "pre_match_input_safe": present,
        "used_for_prediction": present,
        "used_for_prediction_pipeline": present,
        "economic_observation_only": False,
        "available_at_prediction_time": present,
        "prob_raw": None,
        "prob_fair": None,
        "overround": None,
        "family_complete": False,
        "warnings": [],
    }


def strict_quote_entry_for_market(
    strict_bundle: dict[str, Any],
    market: MarketDef,
) -> dict[str, Any]:
    """Normalizza in shape RUN V2 la quota STRICT prodotta dall'adapter V1."""
    raw = (strict_bundle.get("quotes") or {}).get(market.key) or {}
    value = raw.get("value")
    is_real = bool(raw.get("is_real_book_quote"))
    is_derived = bool(raw.get("is_derived"))
    source_columns = raw.get("source_columns") or []

    return {
        "market_key": market.key,
        "export_key": market.export_key,
        "value": value,
        "quote_source": raw.get("source_type"),
        "quote_type": "core_strict",
        "provider": raw.get("provider") or PROVIDER,
        "source_column": ",".join(source_columns) if source_columns else None,
        "quote_snapshot_type": (
            QUOTE_SNAPSHOT_PRE_REFERENCE if value is not None else None
        ),
        "temporal_classification": (
            HISTORICAL_QUOTE_REFERENCE_TIMING if value is not None else None
        ),
        "is_real_quote": is_real,
        "is_derived": is_derived,
        "derivation_method": raw.get("derivation_method"),
        "market_quote_available": value is not None,
        "pre_match_input_safe": value is not None,
        "used_for_prediction": value is not None,
        "used_for_prediction_pipeline": value is not None,
        "economic_observation_only": False,
        "available_at_prediction_time": value is not None,
        "prob_raw": raw.get("prob_raw"),
        "prob_fair": raw.get("prob_fair"),
        "overround": raw.get("overround"),
        "warnings": raw.get("warnings") or [],
    }


def build_run_v2_quote_bundle(match: Any) -> dict[str, Any]:
    """Bundle STRICT a 17 mercati: legacy V1 + enrichment closing/pre-kickoff.

    Nessun layer economic_observation per le nuove RUN: le 12 enrichment
    entrano solo come STRICT e la stessa quota congelata serve al settlement.
    """
    strict = build_match_quote_bundle(
        match, policy_version=HISTORICAL_QUOTE_POLICY_VERSION_V4
    )

    strict_by_market: dict[str, dict[str, Any]] = {}
    for market in CORE_MARKETS:
        entry = strict_quote_entry_for_market(strict, market)
        col = market.strict_quote_columns[0] if market.strict_quote_columns else None

        if col and col in ENRICHMENT_STRICT_QUOTE_COLUMNS:
            enrichment_value = _num(getattr(match, col, None))
            if enrichment_value is not None:
                # Preferenza assoluta: quota reale enrichment (anche su DC).
                entry = _enrichment_strict_entry(market, enrichment_value)
            elif market.strict_quote_derived_from_1x2 and entry.get("value") is not None:
                # DC: fallback derivata 1X2 solo se reale assente.
                entry["warnings"] = list(entry.get("warnings") or []) + [
                    "dc_real_quote_missing_fallback_derived_1x2"
                ]
            else:
                entry = _enrichment_strict_entry(market, None)

        strict_by_market[market.key] = entry

    _apply_family_normalization(strict_by_market)

    strict_available = sum(
        1 for e in strict_by_market.values() if e["value"] is not None
    )
    enrichment_available = sum(
        1
        for m in CORE_MARKETS
        if m.strict_quote_columns
        and m.strict_quote_columns[0] in ENRICHMENT_STRICT_QUOTE_COLUMNS
        and strict_by_market[m.key].get("value") is not None
        and not strict_by_market[m.key].get("is_derived")
    )

    return {
        "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
        "strict_policy_version": HISTORICAL_QUOTE_POLICY_VERSION_V4,
        "reference_timing": HISTORICAL_QUOTE_REFERENCE_TIMING,
        "no_closing_fallback": True,
        "enrichment_temporal_classification": (
            TEMPORAL_CLASSIFICATION_CLOSING_PRE_KICKOFF
        ),
        "enrichment_provider_source": ENRICHMENT_PROVIDER_SOURCE,
        # Bundle V1 integrale: alimenta ancora i mercati legacy del KPI builder.
        "strict_v1_bundle": strict,
        "strict_by_market": strict_by_market,
        # Compat: chiavi economic vuote — nessuna riga economic_observation nuova.
        "economic": {
            "layer": "economic_observation",
            "quotes": {},
            "families": {},
            "counts": {
                "markets_total": 0,
                "markets_with_real_quote": 0,
                "markets_without_quote": 0,
            },
            "pre_match_input_safe": False,
            "used_for_prediction": False,
            "economic_observation_only": True,
            "deprecated_for_new_runs": True,
            "note": (
                "Le 12 enrichment sono STRICT closing/pre-kickoff; "
                "nessun duplicato economic_observation nelle nuove RUN."
            ),
        },
        "counts": {
            "strict_markets_with_quote": strict_available,
            "enrichment_strict_markets_with_quote": enrichment_available,
            "economic_markets_with_quote": 0,
        },
    }


def market_quote_coverage_keys() -> tuple[str, ...]:
    """Chiavi di coverage quote usate nel summary della run."""
    return tuple(f"{market.export_key}__strict" for market in CORE_MARKETS)
