"""Algorithm Registry — definizioni algoritmo per Backtest Engine (stub Step A).

Non importato da servizi runtime esistenti finché non si implementa Step B+.
Per SOT, algorithm_version coincide con model_version esistente.
Vedi docs/BACKTEST_ENGINE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.markets.registry import MARKET_CARDS, MARKET_CORNERS, MARKET_SHOTS_ON_TARGET

AlgorithmStatus = Literal["production", "experimental", "deprecated"]

ALGORITHM_V20_SOT = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
ALGORITHM_V21_SOT = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
ALGORITHM_CORNERS_V1 = "corners_v1_0"
ALGORITHM_CARDS_V1 = "cards_v1_0"


@dataclass(frozen=True)
class AlgorithmSpec:
    market_key: str
    algorithm_version: str
    label: str
    status: AlgorithmStatus
    visible_in_frontend: bool
    input_requirements: dict[str, bool]
    output_schema: dict[str, str]
    trace_schema: dict[str, str]
    engine_entrypoint: str | None


SOT_OUTPUT_SCHEMA: dict[str, str] = {
    "home_team": "predicted_sot",
    "away_team": "predicted_sot",
    "match_total": "derived.sum_predicted_sot",
}

SOT_TRACE_SCHEMA: dict[str, str] = {
    "trace_key": "raw_json.applied_variable_trace",
    "component_tree": "raw_json.components",
}


ALGORITHM_REGISTRY: dict[str, AlgorithmSpec] = {
    ALGORITHM_V20_SOT: AlgorithmSpec(
        market_key=MARKET_SHOTS_ON_TARGET,
        algorithm_version=ALGORITHM_V20_SOT,
        label="SOT v2.0 Lineup Impact",
        status="production",
        visible_in_frontend=True,
        input_requirements={
            "team_stats": True,
            "lineups": True,
            "player_profiles": True,
            "xg": False,
        },
        output_schema=dict(SOT_OUTPUT_SCHEMA),
        trace_schema=dict(SOT_TRACE_SCHEMA),
        engine_entrypoint="app.services.predictions_v20.baseline_v2_0_lineup_impact_service",
    ),
    ALGORITHM_V21_SOT: AlgorithmSpec(
        market_key=MARKET_SHOTS_ON_TARGET,
        algorithm_version=ALGORITHM_V21_SOT,
        label="SOT v2.1 Weighted Components",
        status="production",
        visible_in_frontend=True,
        input_requirements={
            "team_stats": True,
            "lineups": True,
            "player_profiles": True,
            "xg": True,
        },
        output_schema=dict(SOT_OUTPUT_SCHEMA),
        trace_schema=dict(SOT_TRACE_SCHEMA),
        engine_entrypoint="app.services.predictions_v21.baseline_v2_1_weighted_components_service",
    ),
    ALGORITHM_CORNERS_V1: AlgorithmSpec(
        market_key=MARKET_CORNERS,
        algorithm_version=ALGORITHM_CORNERS_V1,
        label="Corner v1.0 (planned)",
        status="experimental",
        visible_in_frontend=False,
        input_requirements={"team_stats": True, "lineups": False},
        output_schema={"match_total": "predicted_corners"},
        trace_schema={"trace_key": "raw_json.applied_variable_trace"},
        engine_entrypoint=None,
    ),
    ALGORITHM_CARDS_V1: AlgorithmSpec(
        market_key=MARKET_CARDS,
        algorithm_version=ALGORITHM_CARDS_V1,
        label="Cartellini v1.0 (planned)",
        status="experimental",
        visible_in_frontend=False,
        input_requirements={"team_stats": True, "lineups": False},
        output_schema={"match_total": "predicted_cards"},
        trace_schema={"trace_key": "raw_json.applied_variable_trace"},
        engine_entrypoint=None,
    ),
}


def get_algorithm(algorithm_version: str) -> AlgorithmSpec | None:
    return ALGORITHM_REGISTRY.get(algorithm_version)


def list_algorithms_for_market(market_key: str) -> list[AlgorithmSpec]:
    return [a for a in ALGORITHM_REGISTRY.values() if a.market_key == market_key]


def list_production_algorithms() -> list[AlgorithmSpec]:
    return [a for a in ALGORITHM_REGISTRY.values() if a.status == "production"]
