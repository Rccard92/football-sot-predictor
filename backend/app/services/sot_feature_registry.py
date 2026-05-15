"""
Registry ufficiale feature per baseline_v1_0_sot (metadati + pesi formula esterni).
I valori numerici sono risolti da v10_feature_resolvers (solo DB, no API live).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FEATURE_REGISTRY_VERSION = "v10_2026_05"
V10_ARCHITECTURE = "feature_registry_explicit_terms_plus_xg"

V11_ARCHITECTURE = "component_based_strict_real_data"
V11_MODEL_STAGE = "offensive_production_only"
V11_MIN_COMPLETED_MATCHES = 5

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
    inputs: dict[str, Any] | list[dict[str, Any]] | None = None
    formula: str = ""
    application_role: str = "direct_formula_component"


FORMULA_TERM_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        feature_key="offensive_production_component",
        label="Produzione offensiva composita",
        source_table="fixture_team_stats",
        source_field="shots_on_target,total_shots,shots_inside_box,shots_outside_box,blocked_shots,shots_off_target",
        api_source="fixtures/statistics + fixtures.goals",
        resolver_name="resolve_offensive_production_component",
        formula="9 segnali normalizzati lega × pesi interni (totale 1.00) × 0.30 formula finale",
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
    "avg_total_shots_for",
    "shot_accuracy_for",
    "avg_inside_box_shots_for",
    "avg_outside_box_shots_for",
    "avg_blocked_shots_for",
    "avg_shots_off_goal_for",
    "avg_goals_for",
    "offensive_trend",
)

OFFENSIVE_INPUT_LABELS: dict[str, str] = {
    "avg_sot_for": "Media tiri in porta fatti",
    "avg_total_shots_for": "Media tiri totali fatti",
    "shot_accuracy_for": "Precisione tiro",
    "avg_inside_box_shots_for": "Media tiri dentro area",
    "avg_outside_box_shots_for": "Media tiri fuori area",
    "avg_blocked_shots_for": "Media tiri bloccati",
    "avg_shots_off_goal_for": "Media tiri fuori dallo specchio",
    "avg_goals_for": "Media goal fatti",
    "offensive_trend": "Trend offensivo recente",
}

_OFFENSIVE_INPUT_SPECS_DATA: tuple[tuple[str, str, str, str, str], ...] = (
    ("avg_sot_for", "shots_on_target", "fixtures/statistics::Shots on Goal", "fixture_team_stats.shots_on_target", "0.30"),
    ("avg_total_shots_for", "total_shots", "fixtures/statistics::Total Shots", "fixture_team_stats.total_shots", "0.18"),
    ("shot_accuracy_for", "derived", "derived", "derived:shots_on_target/total_shots", "0.14"),
    ("avg_inside_box_shots_for", "shots_inside_box", "fixtures/statistics::Shots insidebox", "fixture_team_stats.shots_inside_box", "0.14"),
    ("avg_outside_box_shots_for", "shots_outside_box", "fixtures/statistics::Shots outsidebox", "fixture_team_stats.shots_outside_box", "0.05"),
    ("avg_blocked_shots_for", "blocked_shots", "fixtures/statistics::Blocked Shots", "fixture_team_stats.blocked_shots", "0.05"),
    ("avg_shots_off_goal_for", "shots_off_target", "fixtures/statistics::Shots off Goal", "fixture_team_stats.shots_off_target", "0.04"),
    ("avg_goals_for", "goals", "fixtures::goals", "fixtures.goals", "0.05"),
    ("offensive_trend", "derived", "fixture_team_stats.shots_on_target", "derived:last5_sot_minus_season_sot", "0.05"),
)

OFFENSIVE_COMPONENT_INPUT_SPECS: tuple[FeatureSpec, ...] = tuple(
    FeatureSpec(
        feature_key=key,
        label=OFFENSIVE_INPUT_LABELS[key],
        source_table="fixture_team_stats",
        source_field=field,
        api_source=api,
        resolver_name=f"resolve_offensive_input_{key}",
        formula=f"input interno × {w} (componente offensiva)",
        unit="misto",
        default_weight=float(w),
        required=False,
        fallback_policy="league_normalized_fallback",
        audit_group="offensive_production",
        application_role="component_input",
    )
    for key, field, api, _spath, w in _OFFENSIVE_INPUT_SPECS_DATA
)


def formula_term_spec_by_key(key: str) -> FeatureSpec | None:
    for s in FORMULA_TERM_SPECS:
        if s.feature_key == key:
            return s
    if key == "expected_goals":
        return EXPECTED_GOALS_SPEC
    return None
