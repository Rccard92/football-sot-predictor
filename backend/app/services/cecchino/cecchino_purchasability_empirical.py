"""LEGACY COMPATIBILITY ADAPTER — Affidabilità storica.

Questo file non contiene più la formula. Re-esporta il modulo canonico
``cecchino_historical_reliability`` e mantiene gli alias storici
(empirical / purchasability) per consumer e test non ancora migrati.

Canonico:
  app.services.cecchino.cecchino_historical_reliability
"""

from __future__ import annotations

from app.services.cecchino.cecchino_historical_reliability import (  # noqa: F401
    DATASET_VERSION,
    HISTORICAL_RELIABILITY_VERSION,
    LEGACY_EMPIRICAL_VERSION,
    MAX_PERIODS,
    METRIC_KIND,
    MIN_PERIOD_ROWS,
    MIN_SAMPLE,
    RATING_BANDS,
    SCOPE_GLOBAL,
    SCOPE_LOCAL,
    SUPPORTED_SELECTIONS,
    _class_for_score,
    _explanation,
    build_historical_reliability_for_panel,
    build_historical_reliability_global_index,
    build_historical_reliability_index,
    build_purchasability_rows,
    calculate_historical_reliability,
    calculate_historical_reliability_cohort_metrics,
    clamp,
    get_rating_band,
    is_market_settlement_supported,
    iter_current_kpi_panel_rows,
    panel_item_key,
)

# ---------------------------------------------------------------------------
# Alias legacy (non duplicare la formula)
# ---------------------------------------------------------------------------

EMPIRICAL_VERSION = HISTORICAL_RELIABILITY_VERSION

calculate_empirical_purchasability = calculate_historical_reliability
build_empirical_purchasability_for_panel = build_historical_reliability_for_panel
build_empirical_history_index = build_historical_reliability_index
build_empirical_global_history_index = build_historical_reliability_global_index
calculate_empirical_cohort_metrics = calculate_historical_reliability_cohort_metrics

__all__ = [
    "DATASET_VERSION",
    "EMPIRICAL_VERSION",
    "HISTORICAL_RELIABILITY_VERSION",
    "LEGACY_EMPIRICAL_VERSION",
    "MAX_PERIODS",
    "METRIC_KIND",
    "MIN_PERIOD_ROWS",
    "MIN_SAMPLE",
    "RATING_BANDS",
    "SCOPE_GLOBAL",
    "SCOPE_LOCAL",
    "SUPPORTED_SELECTIONS",
    "_class_for_score",
    "_explanation",
    "build_empirical_global_history_index",
    "build_empirical_history_index",
    "build_empirical_purchasability_for_panel",
    "build_historical_reliability_for_panel",
    "build_historical_reliability_global_index",
    "build_historical_reliability_index",
    "build_purchasability_rows",
    "calculate_empirical_cohort_metrics",
    "calculate_empirical_purchasability",
    "calculate_historical_reliability",
    "calculate_historical_reliability_cohort_metrics",
    "clamp",
    "get_rating_band",
    "is_market_settlement_supported",
    "iter_current_kpi_panel_rows",
    "panel_item_key",
]
