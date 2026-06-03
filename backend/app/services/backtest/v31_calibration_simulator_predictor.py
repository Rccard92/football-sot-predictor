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
from app.services.backtest.v31_calibration_simulator_cohort import CohortStats
from app.services.backtest.v31_calibration_simulator_dynamics import apply_dynamics
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals

VARIANCE_CTX_MIN = 0.75
VARIANCE_CTX_MAX = 1.30
WIDE_TOTAL_MIN = 3.0
WIDE_TOTAL_MAX = 16.0


@dataclass(frozen=True)
class StrategySpec:
    key: str
    label: str
    description: str
    base_weights: dict[str, float]
    context_weights: dict[str, float]
    strategy_family: str = "balanced"
    context_cap_min: float = CONTEXT_CAP_MIN
    context_cap_max: float = CONTEXT_CAP_MAX
    total_league_blend: float = 0.40
    total_min: float = 4.0
    total_max: float = 14.0
    side_cap_min: float = 0.8
    side_cap_max: float = 8.5
    uses_dynamic_bias: bool = False
    uses_dynamics: bool = False


def _spec(
    key: str,
    label: str,
    description: str,
    base_weights: dict[str, float],
    context_weights: dict[str, float],
    *,
    strategy_family: str = "balanced",
    **kwargs: Any,
) -> StrategySpec:
    return StrategySpec(
        key=key,
        label=label,
        description=description,
        base_weights=base_weights,
        context_weights=context_weights,
        strategy_family=strategy_family,
        **kwargs,
    )


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "v31_equal_weights": _spec(
        "v31_equal_weights",
        "v3.1 — Pesi uguali",
        "Base SOT uniforme sui 6 componenti; correttivi macro equilibrati.",
        EQUAL_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="balanced",
    ),
    "v31_core_sot_xg": _spec(
        "v31_core_sot_xg",
        "v3.1 — Core SOT/xG/volume",
        "Peso alto su SOT storici, concessi, xG e volume tiri; context più piatto.",
        CORE_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="balanced",
        context_cap_min=CORE_CONTEXT_CAP_MIN,
        context_cap_max=CORE_CONTEXT_CAP_MAX,
    ),
    "v31_context_adjusted": _spec(
        "v31_context_adjusted",
        "v3.1 — Contesto aggiustato",
        "Base statistica standard + moltiplicatori contestuali cappati.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="balanced",
    ),
    "v31_player_layer_heavy": _spec(
        "v31_player_layer_heavy",
        "v3.1 — Player layer pesante",
        "Enfasi su XI titolare, player layer e assenze nei correttivi macro.",
        DEFAULT_BASE_WEIGHTS,
        PLAYER_LAYER_CONTEXT_WEIGHTS,
        strategy_family="balanced",
    ),
    "v31_home_away_split_heavy": _spec(
        "v31_home_away_split_heavy",
        "v3.1 — Split casa/trasferta",
        "Enfasi su split casa/trasferta in base e contesto.",
        SPLIT_HEAVY_BASE_WEIGHTS,
        SPLIT_HEAVY_CONTEXT_WEIGHTS,
        strategy_family="balanced",
    ),
    "v31_recent_form_heavy": _spec(
        "v31_recent_form_heavy",
        "v3.1 — Forma recente",
        "Enfasi su ultime 5 partite e indice forma recente.",
        FORM_HEAVY_BASE_WEIGHTS,
        FORM_HEAVY_CONTEXT_WEIGHTS,
        strategy_family="balanced",
    ),
    "v31_bias_corrected": _spec(
        "v31_bias_corrected",
        "v3.1 — Bias corretto",
        "Contesto aggiustato + offset dinamico da errore medio fixture precedenti.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="balanced",
        uses_dynamic_bias=True,
    ),
    "v31_low_variance": _spec(
        "v31_low_variance",
        "v3.1 — Bassa varianza",
        "Predizioni conservative: blend lega alto, cap totali stretti.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="conservative",
        context_cap_min=LOW_VARIANCE_CTX_MIN,
        context_cap_max=LOW_VARIANCE_CTX_MAX,
        total_league_blend=LOW_VARIANCE_BLEND,
        total_min=LOW_VARIANCE_TOTAL_MIN,
        total_max=LOW_VARIANCE_TOTAL_MAX,
    ),
    "v31_variance_unlocked": _spec(
        "v31_variance_unlocked",
        "v3.1 — Varianza sbloccata",
        "Blend lega basso, cap larghi, boost da match_open.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="aggressive",
        context_cap_min=VARIANCE_CTX_MIN,
        context_cap_max=VARIANCE_CTX_MAX,
        total_league_blend=0.15,
        total_min=WIDE_TOTAL_MIN,
        total_max=WIDE_TOTAL_MAX,
        side_cap_max=9.5,
        uses_dynamics=True,
    ),
    "v31_big_match_boost": _spec(
        "v31_big_match_boost",
        "v3.1 — Big match boost",
        "Boost quando entrambe le squadre sono offensive (percentili cohort).",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="dynamic",
        total_league_blend=0.10,
        total_min=4.0,
        total_max=WIDE_TOTAL_MAX,
        uses_dynamics=True,
    ),
    "v31_big_vs_weak_push": _spec(
        "v31_big_vs_weak_push",
        "v3.1 — Big vs debole",
        "Spinge il lato favorito contro difesa avversaria fragile.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="dynamic",
        total_league_blend=0.10,
        total_min=4.0,
        total_max=WIDE_TOTAL_MAX,
        uses_dynamics=True,
    ),
    "v31_chaos_game": _spec(
        "v31_chaos_game",
        "v3.1 — Partita aperta",
        "Boost su match aperti: concessioni, xG e ritmo alti.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="aggressive",
        context_cap_min=VARIANCE_CTX_MIN,
        context_cap_max=VARIANCE_CTX_MAX,
        total_league_blend=0.10,
        total_min=4.0,
        total_max=WIDE_TOTAL_MAX,
        uses_dynamics=True,
    ),
    "v31_low_block_guard": _spec(
        "v31_low_block_guard",
        "v3.1 — Low block guard",
        "Penalizza favorita vs avversario a basso ritmo/xG.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="conservative",
        total_league_blend=0.35,
        total_min=5.0,
        total_max=12.0,
        uses_dynamics=True,
    ),
    "v31_extreme_bucket_model": _spec(
        "v31_extreme_bucket_model",
        "v3.1 — Bucket estremi",
        "Classifica profilo match e assegna totale per bucket.",
        DEFAULT_BASE_WEIGHTS,
        CONTEXT_MACRO_WEIGHTS,
        strategy_family="bucket",
        total_league_blend=0.20,
        total_min=WIDE_TOTAL_MIN,
        total_max=WIDE_TOTAL_MAX,
        uses_dynamics=True,
    ),
}


def predict_for_strategy(
    signals: FixtureSignals,
    strategy_key: str,
    *,
    bias_offset: float = 0.0,
    cohort: CohortStats | None = None,
) -> dict[str, Any]:
    spec = STRATEGY_REGISTRY.get(strategy_key)
    if spec is None:
        raise ValueError(f"Unknown strategy: {strategy_key}")

    dyn: dict[str, Any] = {}
    if spec.uses_dynamics:
        dyn = apply_dynamics(strategy_key, signals, cohort)

    pred = predict_fixture_totals(
        signals,
        base_weights=spec.base_weights,
        context_cap_min=spec.context_cap_min,
        context_cap_max=spec.context_cap_max,
        context_weights=spec.context_weights,
        total_league_blend=spec.total_league_blend,
        total_min=spec.total_min,
        total_max=spec.total_max,
        side_cap_min=spec.side_cap_min,
        side_cap_max=spec.side_cap_max,
        bias_offset=bias_offset,
        home_side_multiplier=float(dyn.get("home_side_multiplier") or 1.0),
        away_side_multiplier=float(dyn.get("away_side_multiplier") or 1.0),
        total_boost=float(dyn.get("total_boost") or 0.0),
        bucket_override_total=dyn.get("bucket_override_total"),
        dynamics_trace={
            "boost_applied": round(float(dyn.get("total_boost") or 0.0), 4),
            "boost_reason": dyn.get("boost_reason"),
            "interaction_scores": dyn.get("interaction_scores"),
            "strategy_family": spec.strategy_family,
        },
    )
    trace = pred.get("trace") or {}
    trace["strategy_key"] = strategy_key
    trace["bias_offset_applied"] = round(bias_offset, 4)
    pred["trace"] = trace
    return pred
