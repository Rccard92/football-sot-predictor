"""Costruzione righe mercato CORE STRICT per la RUN V2.

Le probabilita e le quote Cecchino sono lette dagli output dei moduli V1 gia
calcolati: qui non si ricalcola nessuna formula. Per i due soli mercati che la
V1 non conosce (FT O/U 0.5) si leggono i blocchi prodotti dalla capability
opt-in del motore Poisson.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
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
    FAMILY_1X2,
    FAMILY_DC,
    FAMILY_HT_1X2,
    FAMILY_OU,
    LAYER_CORE_STRICT,
    MarketDef,
)
from app.services.cecchino_data_lab.run_v2.settlement import flat_stake_profit

# Selezioni concorrenti per il calcolo della prediction di famiglia.
_PREDICTION_GROUPS: dict[str, tuple[str, ...]] = {
    FAMILY_1X2: (SEL_HOME, SEL_DRAW, SEL_AWAY),
    FAMILY_DC: (SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO),
    FAMILY_HT_1X2: (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT),
    "OU_0_5": (SEL_OVER_0_5, SEL_UNDER_0_5),
    "OU_1_5": (SEL_OVER_1_5, SEL_UNDER_1_5),
    "OU_2_5": (SEL_OVER_2_5, SEL_UNDER_2_5),
    "OU_3_5": (SEL_OVER_3_5, SEL_UNDER_3_5),
}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _prediction_group_key(market: MarketDef) -> str:
    if market.family == FAMILY_OU:
        return f"OU_{(market.line or '').replace('.', '_')}"
    return market.family


def _kpi_rows_by_key(kpi_panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = (kpi_panel or {}).get("rows") or []
    return {
        str(r.get("market_key")): r
        for r in rows
        if isinstance(r, dict) and r.get("market_key")
    }


def _purchasability_by_key(purch: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    markets = (purch or {}).get("markets") or []
    return {
        str(m.get("market_key")): m
        for m in markets
        if isinstance(m, dict) and m.get("market_key")
    }


def _equilibrium_state(balance: dict[str, Any] | None) -> str | None:
    """Estrae lo stato di equilibrio dal payload Balance V5 (top-level)."""
    if not isinstance(balance, dict):
        return None

    def _from_payload(payload: dict[str, Any]) -> str | None:
        pillars = payload.get("pillars")
        if isinstance(pillars, dict):
            f36 = pillars.get("f36")
            if isinstance(f36, dict):
                for key in ("class_key", "class_label", "adjusted_class_key", "adjusted_class_label"):
                    val = f36.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            dominance = pillars.get("dominance")
            if isinstance(dominance, dict):
                for key in ("class_key", "class_label", "class", "label"):
                    val = dominance.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        summary = payload.get("structural_summary")
        if isinstance(summary, str) and summary.strip():
            # Testo composto: usa la geometria se presente, altrimenti il testo intero.
            text = summary.strip()
            if text.lower().startswith("geometria:"):
                part = text.split(".", 1)[0].replace("Geometria:", "").strip()
                return part or text
            return text[:120]
        if isinstance(summary, dict):
            for key in ("state", "label", "structural_state", "summary_label", "class_key"):
                val = summary.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    direct = _from_payload(balance)
    if direct:
        return direct
    values = balance.get("values")
    if isinstance(values, dict):
        return _from_payload(values)
    return None


def _goal_intensity_score(gi_payload: dict[str, Any] | None) -> float | None:
    if not isinstance(gi_payload, dict):
        return None
    for key in (
        "composite_gi_a_strict_core",
        "primary_candidate_score",
        "score",
        "intensity_score",
    ):
        val = _as_float(gi_payload.get(key))
        if val is not None:
            return val
    final_class = gi_payload.get("final_class")
    if isinstance(final_class, dict):
        val = _as_float(final_class.get("score"))
        if val is not None:
            return val
    values = gi_payload.get("values")
    if isinstance(values, dict):
        for key in ("composite_gi_a_strict_core", "primary_candidate_score", "score"):
            val = _as_float(values.get(key))
            if val is not None:
                return val
    return None


def equilibrium_state_from_balance(balance: dict[str, Any] | None) -> str | None:
    """API pubblica usata anche dall'export per run gia persistite."""
    return _equilibrium_state(balance)


def _block_values(block: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    summary = block.get("summary") or {}
    return (
        _as_float(summary.get("final_probability")),
        _as_float(block.get("final_odd")),
        _as_float(summary.get("overall_reliability")),
    )


def _model_probability(
    market: MarketDef,
    *,
    kpi_row: dict[str, Any],
    goal_markets: dict[str, Any],
    ou_05_markets: dict[str, Any],
    ht_1x2_markets: dict[str, Any],
) -> tuple[float | None, float | None, float | None]:
    """(probability, quota_cecchino, confidence) dagli output gia calcolati."""
    if market.key in (SEL_OVER_0_5, SEL_UNDER_0_5):
        return _block_values((ou_05_markets or {}).get(market.key) or {})

    # HT 1X2 dalla famiglia normalizzata, cosi le tre righe sommano a 1.
    if market.family == FAMILY_HT_1X2:
        return _block_values((ht_1x2_markets or {}).get(market.key) or {})

    probability = _as_float(kpi_row.get("prob_cecchino"))
    quota = _as_float(kpi_row.get("quota_cecchino"))

    block = (goal_markets or {}).get(market.key) or {}
    summary = block.get("summary") or {}
    confidence = _as_float(summary.get("overall_reliability"))
    if probability is None:
        probability = _as_float(summary.get("final_probability"))
    if quota is None:
        quota = _as_float(block.get("final_odd"))

    return probability, quota, confidence


def _family_predictions(
    probabilities: dict[str, float | None],
) -> dict[str, str | None]:
    """Selezione a probabilita massima per ciascuna famiglia."""
    out: dict[str, str | None] = {}
    for group_key, keys in _PREDICTION_GROUPS.items():
        best_key: str | None = None
        best_prob: float | None = None
        for key in keys:
            prob = probabilities.get(key)
            if prob is None:
                continue
            if best_prob is None or prob > best_prob:
                best_prob = prob
                best_key = key
        out[group_key] = best_key
    return out


def build_core_strict_market_rows(
    *,
    kpi_panel: dict[str, Any] | None,
    goal_markets: dict[str, Any] | None,
    ou_05_markets: dict[str, Any] | None,
    ht_1x2_markets: dict[str, Any] | None,
    strict_by_market: dict[str, dict[str, Any]],
    balance: dict[str, Any] | None,
    gi_payload: dict[str, Any] | None,
    purchasability: dict[str, Any] | None,
    outcomes: dict[str, dict[str, Any]],
    signal_index: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Una riga CORE STRICT per ciascuno dei mercati CORE V2."""
    kpi_rows = _kpi_rows_by_key(kpi_panel)
    purch_rows = _purchasability_by_key(purchasability)
    equilibrium = _equilibrium_state(balance)
    gi_score = _goal_intensity_score(gi_payload)
    signals = signal_index or {}

    probabilities: dict[str, float | None] = {}
    quotas: dict[str, float | None] = {}
    confidences: dict[str, float | None] = {}
    for market in CORE_MARKETS:
        prob, quota, conf = _model_probability(
            market,
            kpi_row=kpi_rows.get(market.key) or {},
            goal_markets=goal_markets or {},
            ou_05_markets=ou_05_markets or {},
            ht_1x2_markets=ht_1x2_markets or {},
        )
        probabilities[market.key] = prob
        quotas[market.key] = quota
        confidences[market.key] = conf

    predictions = _family_predictions(probabilities)

    rows: list[dict[str, Any]] = []
    for market in CORE_MARKETS:
        kpi_row = kpi_rows.get(market.key) or {}
        quote = strict_by_market.get(market.key) or {}
        purch = purch_rows.get(market.key) or {}
        outcome = outcomes.get(market.key) or {}
        sig = signals.get(market.key) or {}

        quota_book = _as_float(quote.get("value"))
        won = outcome.get("won")
        group_key = _prediction_group_key(market)
        predicted_key = predictions.get(group_key)

        rows.append(
            {
                "market_key": market.key,
                "export_key": market.export_key,
                "market_label": market.label,
                "market_family": market.family,
                "period": market.period,
                "line": market.line,
                "observation_layer": LAYER_CORE_STRICT,
                # Prediction di famiglia + probabilita della singola selezione.
                "prediction": predicted_key,
                "is_predicted_selection": predicted_key == market.key,
                "probability": probabilities.get(market.key),
                "quota_cecchino": quotas.get(market.key),
                "confidence": confidences.get(market.key),
                "kpi_rating": kpi_row.get("rating"),
                "edge_pct": _as_float(kpi_row.get("edge_pct")),
                "vantaggio_prob": _as_float(kpi_row.get("vantaggio_prob")),
                "buyability_score": _as_float(purch.get("score")),
                "buyability_class": purch.get("class"),
                "buyability_status": purch.get("status"),
                "signal_active": bool(sig.get("signal_active")),
                "signal_sources_json": sig.get("signal_sources_json"),
                "equilibrium_state": equilibrium,
                "goal_intensity_score": gi_score,
                "market_available": probabilities.get(market.key) is not None,
                "market_quote_available": quota_book is not None,
                "quota_book": quota_book,
                "prob_book_raw": _as_float(quote.get("prob_raw")),
                "prob_book_fair": _as_float(quote.get("prob_fair")),
                "is_real_quote": bool(quote.get("is_real_quote")),
                "is_derived_quote": bool(quote.get("is_derived")),
                "derivation_method": quote.get("derivation_method"),
                "quote_source": quote.get("quote_source"),
                "quote_type": quote.get("quote_type"),
                "source_column": quote.get("source_column"),
                "quote_snapshot_type": quote.get("quote_snapshot_type"),
                "pre_match_input_safe": bool(quote.get("pre_match_input_safe")),
                "used_for_prediction": bool(quote.get("used_for_prediction")),
                "economic_observation_only": False,
                "outcome": outcome.get("outcome"),
                "won": won,
                "flat_stake_profit": flat_stake_profit(won=won, quota=quota_book),
                "result_reason": outcome.get("result_reason"),
            }
        )

    return rows


def frozen_probabilities(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """Probabilita congelate per mercato, input del benchmark economico."""
    return {r["market_key"]: r.get("probability") for r in rows}
