"""Layer ECONOMIC BENCHMARK OBSERVATION (RUN V2).

Confronta una prediction GIA CONGELATA con le quote near-closing `*_last_seen`.
Non e una prediction e non va chiamata tale: serve solo a stimare se quella
prediction sarebbe stata economicamente interessante a quella quota.

Regole non negoziabili:
- riceve in input solo output gia freezati, mai contesti o storico;
- non retroagisce in alcun modo sulla prediction;
- ogni metrica ha prefisso `economic_benchmark_` e porta sempre
  `used_for_prediction=false` e `pre_match_input_safe=false`;
- nessuna metrica puo chiamarsi `strict_*`, `deployable_*` o `roi` nudo.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKET_BY_KEY,
    LAYER_ECONOMIC,
    QUOTE_SNAPSHOT_LAST_SEEN,
)
from app.services.cecchino_data_lab.run_v2.settlement import flat_stake_profit

ECONOMIC_BENCHMARK_VERSION = "cecchino_run_v2_economic_benchmark_v1"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def build_economic_benchmark_row(
    *,
    market_key: str,
    frozen_probability: float | None,
    economic_quote: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Riga di benchmark economico per un mercato.

    `frozen_probability` e la probabilita gia congelata dal Cecchino: viene
    letta, mai ricalcolata a partire dalla quota.
    """
    market = CORE_MARKET_BY_KEY.get(market_key)
    quota = _as_float(economic_quote.get("value"))
    prob = _as_float(frozen_probability)
    won = outcome.get("won")

    benchmark_value = None
    if prob is not None and quota is not None:
        benchmark_value = round(prob * quota - 1.0, 6)

    profit = flat_stake_profit(won=won, quota=quota)
    # Su puntata piatta di 1 unita il ROI della singola giocata coincide con il
    # profitto; resta esplicito perche a valle venga aggregato come ROI.
    roi = None if profit is None else round(profit, 6)

    return {
        "market_key": market_key,
        "export_key": market.export_key if market else market_key,
        "observation_layer": LAYER_ECONOMIC,
        "version": ECONOMIC_BENCHMARK_VERSION,
        "quote_snapshot_type": QUOTE_SNAPSHOT_LAST_SEEN,
        "quota_book": quota,
        "quote_source": economic_quote.get("quote_source"),
        "source_column": economic_quote.get("source_column"),
        "is_real_quote": bool(economic_quote.get("is_real_quote")),
        "is_derived_quote": False,
        "market_quote_available": quota is not None,
        "prob_book_raw": economic_quote.get("prob_raw"),
        "prob_book_fair": economic_quote.get("prob_fair"),
        "frozen_probability": prob,
        "economic_benchmark_value": benchmark_value,
        "economic_benchmark_profit": profit,
        "economic_benchmark_roi": roi,
        "outcome": outcome.get("outcome"),
        "won": won,
        "result_reason": outcome.get("result_reason"),
        # Marcature obbligatorie del layer.
        "pre_match_input_safe": False,
        "used_for_prediction": False,
        "economic_observation_only": True,
        "available_at_prediction_time": "not_certified",
    }


def build_economic_benchmark_rows(
    *,
    economic_bundle: dict[str, Any],
    frozen_probabilities: dict[str, float | None],
    outcomes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Righe di benchmark per tutti i mercati con colonna near-closing.

    Il mercato resta presente anche quando la quota e NULL: cambia solo
    `market_quote_available`, non l'inclusione.
    """
    rows: list[dict[str, Any]] = []
    for market_key, quote in (economic_bundle.get("quotes") or {}).items():
        rows.append(
            build_economic_benchmark_row(
                market_key=market_key,
                frozen_probability=frozen_probabilities.get(market_key),
                economic_quote=quote,
                outcome=outcomes.get(market_key) or {},
            )
        )
    rows.sort(key=lambda r: r["market_key"])
    return rows


def summarize_economic_benchmark(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregato di run, sempre etichettato come benchmark."""
    settled = [r for r in rows if r.get("economic_benchmark_profit") is not None]
    total_profit = sum(float(r["economic_benchmark_profit"]) for r in settled)
    wins = sum(1 for r in settled if r.get("won") is True)

    return {
        "version": ECONOMIC_BENCHMARK_VERSION,
        "quote_snapshot_type": QUOTE_SNAPSHOT_LAST_SEEN,
        "used_for_prediction": False,
        "pre_match_input_safe": False,
        "economic_observation_only": True,
        "rows_total": len(rows),
        "rows_with_quote": sum(1 for r in rows if r.get("market_quote_available")),
        "rows_settled": len(settled),
        "wins": wins,
        "losses": len(settled) - wins,
        "economic_benchmark_profit_total": round(total_profit, 4),
        "economic_benchmark_roi_avg": (
            round(total_profit / len(settled), 6) if settled else None
        ),
    }
