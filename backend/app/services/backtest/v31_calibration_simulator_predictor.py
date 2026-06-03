"""Predizione numerica SOT per simulatore predittivo v3.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.backtest.v31_calibration_simulator_base_sot import (
    CONTEXT_CAP_MAX,
    CONTEXT_CAP_MIN,
    CONTEXT_MACRO_WEIGHTS,
    CORE_BASE_WEIGHTS,
    CORE_CONTEXT_CAP_MAX,
    CORE_CONTEXT_CAP_MIN,
    DEFAULT_BASE_WEIGHTS,
    EQUAL_BASE_WEIGHTS,
    FORM_HEAVY_BASE_WEIGHTS,
    FORM_HEAVY_CONTEXT_WEIGHTS,
    LOW_VARIANCE_BLEND,
    LOW_VARIANCE_CTX_MAX,
    LOW_VARIANCE_CTX_MIN,
    LOW_VARIANCE_TOTAL_MAX,
    LOW_VARIANCE_TOTAL_MIN,
    PLAYER_LAYER_CONTEXT_WEIGHTS,
    SPLIT_HEAVY_BASE_WEIGHTS,
    SPLIT_HEAVY_CONTEXT_WEIGHTS,
    predict_fixture_totals,
)
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals


@dataclass(frozen=True)
class StrategySpec:
    key: str
    label: str
    description: str
    base_weights: dict[str, float]
    context_weights: dict[str, float]
    context_cap_min: float = CONTEXT_CAP_MIN
    context_cap_max: float = CONTEXT_CAP_MAX
    total_league_blend: float = 0.40
    total_min: float = 4.0
    total_max: float = 14.0
    uses_dynamic_bias: bool = False


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "v31_equal_weights": StrategySpec(
        key="v31_equal_weights",
        label="v3.1 — Pesi uguali",
        description="Base SOT uniforme sui 6 componenti; correttivi macro equilibrati.",
        base_weights=EQUAL_BASE_WEIGHTS,
        context_weights=CONTEXT_MACRO_WEIGHTS,
    ),
    "v31_core_sot_xg": StrategySpec(
        key="v31_core_sot_xg",
        label="v3.1 — Core SOT/xG/volume",
        description="Peso alto su SOT storici, concessi, xG e volume tiri; context più piatto.",
        base_weights=CORE_BASE_WEIGHTS,
        context_weights=CONTEXT_MACRO_WEIGHTS,
        context_cap_min=CORE_CONTEXT_CAP_MIN,
        context_cap_max=CORE_CONTEXT_CAP_MAX,
    ),
    "v31_context_adjusted": StrategySpec(
        key="v31_context_adjusted",
        label="v3.1 — Contesto aggiustato",
        description="Base statistica standard + moltiplicatori contestuali cappati.",
        base_weights=DEFAULT_BASE_WEIGHTS,
        context_weights=CONTEXT_MACRO_WEIGHTS,
    ),
    "v31_player_layer_heavy": StrategySpec(
        key="v31_player_layer_heavy",
        label="v3.1 — Player layer pesante",
        description="Enfasi su XI titolare, player layer e assenze nei correttivi macro.",
        base_weights=DEFAULT_BASE_WEIGHTS,
        context_weights=PLAYER_LAYER_CONTEXT_WEIGHTS,
    ),
    "v31_home_away_split_heavy": StrategySpec(
        key="v31_home_away_split_heavy",
        label="v3.1 — Split casa/trasferta",
        description="Enfasi su split casa/trasferta in base e contesto.",
        base_weights=SPLIT_HEAVY_BASE_WEIGHTS,
        context_weights=SPLIT_HEAVY_CONTEXT_WEIGHTS,
    ),
    "v31_recent_form_heavy": StrategySpec(
        key="v31_recent_form_heavy",
        label="v3.1 — Forma recente",
        description="Enfasi su ultime 5 partite e indice forma recente.",
        base_weights=FORM_HEAVY_BASE_WEIGHTS,
        context_weights=FORM_HEAVY_CONTEXT_WEIGHTS,
    ),
    "v31_bias_corrected": StrategySpec(
        key="v31_bias_corrected",
        label="v3.1 — Bias corretto",
        description="Come contesto aggiustato + offset dinamico da errore medio fixture precedenti.",
        base_weights=DEFAULT_BASE_WEIGHTS,
        context_weights=CONTEXT_MACRO_WEIGHTS,
        uses_dynamic_bias=True,
    ),
    "v31_low_variance": StrategySpec(
        key="v31_low_variance",
        label="v3.1 — Bassa varianza",
        description="Predizioni più conservative: blend lega alto, cap totali stretti.",
        base_weights=DEFAULT_BASE_WEIGHTS,
        context_weights=CONTEXT_MACRO_WEIGHTS,
        context_cap_min=LOW_VARIANCE_CTX_MIN,
        context_cap_max=LOW_VARIANCE_CTX_MAX,
        total_league_blend=LOW_VARIANCE_BLEND,
        total_min=LOW_VARIANCE_TOTAL_MIN,
        total_max=LOW_VARIANCE_TOTAL_MAX,
    ),
}


def predict_for_strategy(
    signals: FixtureSignals,
    strategy_key: str,
    *,
    bias_offset: float = 0.0,
) -> dict[str, Any]:
    spec = STRATEGY_REGISTRY.get(strategy_key)
    if spec is None:
        raise ValueError(f"Unknown strategy: {strategy_key}")
    pred = predict_fixture_totals(
        signals,
        base_weights=spec.base_weights,
        context_cap_min=spec.context_cap_min,
        context_cap_max=spec.context_cap_max,
        context_weights=spec.context_weights,
        total_league_blend=spec.total_league_blend,
        total_min=spec.total_min,
        total_max=spec.total_max,
        bias_offset=bias_offset,
    )
    trace = pred.get("trace") or {}
    trace["strategy_key"] = strategy_key
    trace["bias_offset_applied"] = round(bias_offset, 4)
    pred["trace"] = trace
    return pred
