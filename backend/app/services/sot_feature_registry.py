"""
Registry ufficiale feature per baseline_v1_0_sot (metadati + pesi formula esterni).
I valori numerici sono risolti da v10_feature_resolvers (solo DB, no API live).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FEATURE_REGISTRY_VERSION = "v10_2026_05"
V10_ARCHITECTURE = "feature_registry_explicit_terms_plus_xg"

WEIGHT_OFFENSIVE = 0.30


@dataclass(frozen=True)
class FeatureSpec:
    feature_key: str
    label: str
    source_table: str
    source_field: str
    api_source: str
    resolver_name: str
    formula: str
    unit: str
    default_weight: float
    required: bool
    fallback_policy: str
    audit_group: str
    application_role: str = "direct_formula_component"


@dataclass
class ResolvedFeature:
    key: str
    label: str
    value: float | None
    contribution: float
    weight: float
    source_table: str
    source_field: str
    api_source: str
    source_path: str
    sample_count: int
    fallback_used: bool
    fallback_reason: str | None
    status: str
    no_data_leakage: bool = True
    inputs: dict[str, Any] | None = None
    formula: str = ""
    application_role: str = "direct_formula_component"


FORMULA_TERM_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        feature_key="offensive_production_component",
        label="Produzione offensiva (componente)",
        source_table="fixture_team_stats",
        source_field="shots_on_target,total_shots,shots_inside_box,shots_outside_box",
        api_source="fixtures/statistics + fixtures.goals",
        resolver_name="resolve_offensive_production_component",
        formula="blend pesato segnali offensivi (cap ±0.75) × 0.30",
        unit="tiri in porta",
        default_weight=WEIGHT_OFFENSIVE,
        required=True,
        fallback_policy="prudential_component_fallback",
        audit_group="offensive_production",
    ),
    FeatureSpec(
        feature_key="opp_avg_sot_conceded",
        label="Tiri in porta concessi dall'avversario (stagione)",
        source_table="fixture_team_stats",
        source_field="shots_on_target",
        api_source="fixtures/statistics::Shots on Goal",
        resolver_name="resolve_opponent_season_avg_sot_conceded",
        formula="media SOT concessi avversario (stagione) × 0.25",
        unit="tiri in porta",
        default_weight=0.25,
        required=True,
        fallback_policy="league_avg_then_zero",
        audit_group="baseline_external",
    ),
    FeatureSpec(
        feature_key="team_split_avg_sot_for",
        label="SOT fatti in split casa/trasferta",
        source_table="fixture_team_stats",
        source_field="shots_on_target",
        api_source="fixtures/statistics::Shots on Goal",
        resolver_name="resolve_team_home_away_avg_sot_for",
        formula="media SOT fatti in contesto casa/trasferta × 0.15",
        unit="tiri in porta",
        default_weight=0.15,
        required=True,
        fallback_policy="season_avg_then_league",
        audit_group="baseline_external",
    ),
    FeatureSpec(
        feature_key="opp_split_avg_sot_conceded",
        label="SOT concessi avversario in split casa/trasferta",
        source_table="fixture_team_stats",
        source_field="shots_on_target",
        api_source="fixtures/statistics::Shots on Goal",
        resolver_name="resolve_opponent_home_away_avg_sot_conceded",
        formula="media SOT concessi avversario in split × 0.10",
        unit="tiri in porta",
        default_weight=0.10,
        required=True,
        fallback_policy="season_conceded_then_league",
        audit_group="baseline_external",
    ),
    FeatureSpec(
        feature_key="team_last5_avg_sot_for",
        label="SOT fatti ultime 5",
        source_table="fixture_team_stats",
        source_field="shots_on_target",
        api_source="fixtures/statistics::Shots on Goal",
        resolver_name="resolve_last5_avg_sot_for",
        formula="media SOT fatti ultime 5 × 0.10",
        unit="tiri in porta",
        default_weight=0.10,
        required=True,
        fallback_policy="season_avg_then_league",
        audit_group="baseline_external",
    ),
    FeatureSpec(
        feature_key="opp_last5_avg_sot_conceded",
        label="SOT concessi avversario ultime 5",
        source_table="fixture_team_stats",
        source_field="shots_on_target",
        api_source="fixtures/statistics::Shots on Goal",
        resolver_name="resolve_opponent_last5_avg_sot_conceded",
        formula="media SOT concessi avversario ultime 5 × 0.10",
        unit="tiri in porta",
        default_weight=0.10,
        required=True,
        fallback_policy="season_conceded_then_league",
        audit_group="baseline_external",
    ),
)

EXPECTED_GOALS_SPEC = FeatureSpec(
    feature_key="expected_goals",
    label="xG / Expected goals",
    source_table="fixture_team_stats",
    source_field="expected_goals",
    api_source="fixtures/statistics::expected_goals",
    resolver_name="resolve_expected_goals_adjustment",
    formula="base_explicit_sot * xg_adjustment_pct",
    unit="xG medi",
    default_weight=0.10,
    required=False,
    fallback_policy="contribution_zero",
    audit_group="xg_adjustment",
)

OFFENSIVE_INPUT_KEYS: tuple[str, ...] = (
    "avg_sot_for",
    "avg_goals_for",
    "offensive_trend",
    "shot_accuracy_for",
    "avg_total_shots_for",
    "avg_inside_box_shots_for",
    "avg_outside_box_shots_for",
)

OFFENSIVE_INPUT_LABELS: dict[str, str] = {
    "avg_sot_for": "Media tiri in porta fatti (stagione)",
    "avg_goals_for": "Media goal fatti",
    "offensive_trend": "Trend offensivo ultime vs stagione",
    "shot_accuracy_for": "Precisione tiro (SOT / tiri totali)",
    "avg_total_shots_for": "Media tiri totali fatti",
    "avg_inside_box_shots_for": "Media tiri dentro area",
    "avg_outside_box_shots_for": "Media tiri fuori area",
}


def formula_term_spec_by_key(key: str) -> FeatureSpec | None:
    for s in FORMULA_TERM_SPECS:
        if s.feature_key == key:
            return s
    if key == "expected_goals":
        return EXPECTED_GOALS_SPEC
    return None
