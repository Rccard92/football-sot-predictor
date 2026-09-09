"""Bundle quote dual-track RUN V2.

Due binari distinti e non mescolabili:

- STRICT: prodotto invariato dall'adapter V1 con policy `bet365_pre_reference_v1`.
  Sono le uniche quote ammesse come input del Cecchino.
- ECONOMIC: le 12 colonne `*_last_seen`, near-closing. Non certificabili come
  pre-match safe, quindi utilizzabili solo per il benchmark economico a
  prediction gia congelata.

Nessuna quota reale viene mai sostituita da una derivata, e nessun valore viene
alterato: si legge la colonna, si arrotonda solo in fase di serializzazione.
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
    FAMILY_DC,
    FAMILY_HT_1X2,
    FAMILY_OU,
    LAYER_ECONOMIC,
    QUOTE_SNAPSHOT_LAST_SEEN,
    QUOTE_SNAPSHOT_PRE_REFERENCE,
    RUN_V2_QUOTE_POLICY_VERSION,
    MarketDef,
)

PROVIDER = "Bet365"
ECONOMIC_QUOTE_SOURCE = "bet365_enrichment_last_seen"
ECONOMIC_PROVIDER_SOURCE = "bet365 enrichment CSV (last_seen)"

# available_at_prediction_time per le quote near-closing: non certificato.
AVAILABILITY_NOT_CERTIFIED = "not_certified"


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


def _economic_quote_entry(
    market: MarketDef,
    value: float | None,
) -> dict[str, Any]:
    return {
        "market_key": market.key,
        "export_key": market.export_key,
        "value": round(value, 3) if value is not None else None,
        "quote_source": ECONOMIC_QUOTE_SOURCE if value is not None else None,
        "quote_type": LAYER_ECONOMIC,
        "provider": PROVIDER,
        "source_column": market.economic_quote_column,
        "quote_snapshot_type": QUOTE_SNAPSHOT_LAST_SEEN,
        "is_real_quote": value is not None,
        "is_derived": False,
        "derivation_method": None,
        "market_quote_available": value is not None,
        # Vincoli anti-leakage: mai input, mai prediction.
        "pre_match_input_safe": False,
        "used_for_prediction": False,
        "economic_observation_only": True,
        "available_at_prediction_time": AVAILABILITY_NOT_CERTIFIED,
        "prob_raw": None,
        "prob_fair": None,
        "overround": None,
        "family_complete": False,
    }


def _economic_family_groups() -> dict[str, list[MarketDef]]:
    """Famiglie economiche per il calcolo di overround e fair probability."""
    groups: dict[str, list[MarketDef]] = {}
    for m in CORE_MARKETS:
        if not m.has_economic_quote:
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
) -> dict[str, dict[str, Any]]:
    """Overround e fair probability, solo su famiglie complete.

    Per DC la somma delle tre probabilita vale 2 (ogni esito e coperto da due
    delle tre selezioni), quindi il divisore e `sum / 2`.
    """
    families: dict[str, dict[str, Any]] = {}

    for fam_key, markets in _economic_family_groups().items():
        entries = [quotes[m.key] for m in markets if m.key in quotes]
        values = [e["value"] for e in entries]
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

        families[fam_key] = {
            "markets": [m.key for m in markets],
            "available": complete,
            "overround": round(raw_sum, 6) if complete and raw_sum else None,
            "quote_snapshot_type": QUOTE_SNAPSHOT_LAST_SEEN,
            "pre_match_input_safe": False,
            "used_for_prediction": False,
        }

    return families


def build_economic_quote_bundle(match: Any) -> dict[str, Any]:
    """Quote near-closing per il layer di benchmark economico."""
    quotes: dict[str, dict[str, Any]] = {}
    for market in CORE_MARKETS:
        if not market.has_economic_quote:
            continue
        value = _num(getattr(match, market.economic_quote_column, None))
        quotes[market.key] = _economic_quote_entry(market, value)

    families = _apply_family_normalization(quotes)
    available = sum(1 for q in quotes.values() if q["value"] is not None)

    return {
        "layer": LAYER_ECONOMIC,
        "provider": PROVIDER,
        "provider_source": ECONOMIC_PROVIDER_SOURCE,
        "quote_snapshot_type": QUOTE_SNAPSHOT_LAST_SEEN,
        "pre_match_input_safe": False,
        "used_for_prediction": False,
        "economic_observation_only": True,
        "available_at_prediction_time": AVAILABILITY_NOT_CERTIFIED,
        "quotes": quotes,
        "families": families,
        "counts": {
            "markets_total": len(quotes),
            "markets_with_real_quote": available,
            "markets_without_quote": len(quotes) - available,
        },
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
        "quote_snapshot_type": QUOTE_SNAPSHOT_PRE_REFERENCE if value is not None else None,
        "is_real_quote": is_real,
        "is_derived": is_derived,
        "derivation_method": raw.get("derivation_method"),
        "market_quote_available": value is not None,
        "pre_match_input_safe": value is not None,
        "used_for_prediction": value is not None,
        "economic_observation_only": False,
        "available_at_prediction_time": value is not None,
        "prob_raw": raw.get("prob_raw"),
        "prob_fair": raw.get("prob_fair"),
        "overround": raw.get("overround"),
        "warnings": raw.get("warnings") or [],
    }


def build_run_v2_quote_bundle(match: Any) -> dict[str, Any]:
    """Bundle completo: binario STRICT (V1 invariato) + binario ECONOMIC."""
    strict = build_match_quote_bundle(
        match, policy_version=HISTORICAL_QUOTE_POLICY_VERSION_V4
    )
    economic = build_economic_quote_bundle(match)

    strict_by_market: dict[str, dict[str, Any]] = {}
    for market in CORE_MARKETS:
        entry = strict_quote_entry_for_market(strict, market)
        # Un mercato senza quota pre-reference non ne riceve una surrogata.
        if entry["value"] is None and not market.has_strict_real_quote:
            if not market.strict_quote_derived_from_1x2:
                entry["quote_source"] = None
        strict_by_market[market.key] = entry

    strict_available = sum(
        1 for e in strict_by_market.values() if e["value"] is not None
    )

    return {
        "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
        "strict_policy_version": HISTORICAL_QUOTE_POLICY_VERSION_V4,
        "reference_timing": HISTORICAL_QUOTE_REFERENCE_TIMING,
        "no_closing_fallback": True,
        # Bundle V1 integrale: e quello che alimenta KPI e Acquistabilita CORE.
        "strict_v1_bundle": strict,
        "strict_by_market": strict_by_market,
        "economic": economic,
        "counts": {
            "strict_markets_with_quote": strict_available,
            "economic_markets_with_quote": economic["counts"]["markets_with_real_quote"],
        },
    }


def market_quote_coverage_keys() -> tuple[str, ...]:
    """Chiavi di coverage quote usate nel summary della run."""
    keys: list[str] = []
    for market in CORE_MARKETS:
        if market.has_strict_real_quote or market.strict_quote_derived_from_1x2:
            keys.append(f"{market.export_key}__strict")
        if market.has_economic_quote:
            keys.append(f"{market.export_key}__economic")
    return tuple(keys)
