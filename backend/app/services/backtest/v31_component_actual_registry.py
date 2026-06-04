"""Registry variabili component_trace v3.1 e tipo confronto actual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActualComparisonType = Literal["direct", "derived", "diagnostic_only", "unavailable"]

MACRO_AREA_LABELS: dict[str, str] = {
    "offensive_production": "Produzione offensiva",
    "opponent_defensive_resistance": "Resistenza difensiva avversario",
    "recent_form": "Forma recente",
    "chance_quality": "Qualità occasioni",
    "pace_control": "Ritmo e controllo",
    "home_away_split": "Split casa/trasferta",
    "player_layer": "Player layer",
    "injuries_unavailable": "Assenze e indisponibili",
    "lineups": "Formazioni",
    "match_dynamics": "Dinamiche match",
    "data_quality": "Qualità dati",
}


@dataclass(frozen=True)
class VariableSpec:
    key: str
    label: str
    macro_area: str
    actual_comparison_type: ActualComparisonType
    source: str
    uses_opponent: bool = False
    derived_from: tuple[str, ...] | None = None


BASE_VARIABLES: tuple[VariableSpec, ...] = (
    VariableSpec(
        "avg_sot_for",
        "Media tiri in porta fatti",
        "offensive_production",
        "direct",
        "team_raw.avg_sot_for",
    ),
    VariableSpec(
        "avg_total_shots_for",
        "Volume tiri totali fatti",
        "offensive_production",
        "direct",
        "team_raw.avg_total_shots_for",
    ),
    VariableSpec(
        "avg_xg_for",
        "Media xG fatti",
        "offensive_production",
        "direct",
        "team_raw.avg_xg_for",
    ),
    VariableSpec(
        "last5_avg_sot_for",
        "Media SOT ultime 5",
        "recent_form",
        "direct",
        "team_raw.last5_avg_sot_for",
    ),
    VariableSpec(
        "home_away_split_sot_for",
        "Split casa/trasferta SOT",
        "home_away_split",
        "direct",
        "team_raw.home_away_split_sot_for",
    ),
    VariableSpec(
        "opponent_conceded_sot_avg",
        "Media SOT concessi avversario",
        "opponent_defensive_resistance",
        "direct",
        "opponent.avg_sot_against",
        uses_opponent=True,
    ),
    VariableSpec(
        "avg_sot_against",
        "Media SOT subiti",
        "opponent_defensive_resistance",
        "direct",
        "team_raw.avg_sot_against",
    ),
    VariableSpec(
        "avg_total_shots_against",
        "Volume tiri subiti",
        "opponent_defensive_resistance",
        "direct",
        "team_raw.avg_total_shots_against",
    ),
    VariableSpec(
        "xg_to_sot",
        "Conversione xG → SOT",
        "offensive_production",
        "derived",
        "derived.xg_to_sot",
        derived_from=("avg_xg_for",),
    ),
    VariableSpec(
        "shots_to_sot",
        "Conversione tiri → SOT",
        "offensive_production",
        "derived",
        "derived.shots_to_sot",
        derived_from=("avg_total_shots_for",),
    ),
    VariableSpec(
        "shot_accuracy",
        "Precisione tiro (SOT/tiri)",
        "offensive_production",
        "derived",
        "fixture_team_stats.shots_on_target/total_shots",
    ),
    VariableSpec(
        "xg_per_shot",
        "xG per tiro",
        "offensive_production",
        "derived",
        "fixture_team_stats.expected_goals/total_shots",
    ),
    VariableSpec(
        "shots_inside_box",
        "Tiri dentro area",
        "offensive_production",
        "direct",
        "fixture_team_stats.shots_inside_box",
    ),
    VariableSpec(
        "shots_outside_box",
        "Tiri fuori area",
        "offensive_production",
        "direct",
        "fixture_team_stats.shots_outside_box",
    ),
    VariableSpec(
        "blocked_shots",
        "Tiri bloccati",
        "offensive_production",
        "direct",
        "fixture_team_stats.blocked_shots",
    ),
    VariableSpec(
        "shots_off_goal",
        "Tiri fuori bersaglio",
        "offensive_production",
        "direct",
        "fixture_team_stats.shots_off_goal",
    ),
)

CONTEXT_MACRO_KEYS: tuple[str, ...] = (
    "recent_form_index",
    "chance_quality_index",
    "pace_control_index",
    "home_away_split_index",
    "player_layer_index",
    "injuries_unavailable_index",
    "lineups_index",
)

CONTEXT_VARIABLES: tuple[VariableSpec, ...] = tuple(
    VariableSpec(
        k,
        MACRO_AREA_LABELS.get(k.replace("_index", ""), k),
        k.replace("_index", ""),
        "diagnostic_only",
        f"macro.{k}",
    )
    for k in CONTEXT_MACRO_KEYS
)

MATCH_LEVEL_VARIABLES: tuple[VariableSpec, ...] = (
    VariableSpec("high_total_signal", "Segnale high total", "match_dynamics", "diagnostic_only", "trace.high_total_signal"),
    VariableSpec("chaos_signal", "Segnale chaos", "match_dynamics", "diagnostic_only", "trace.chaos_signal"),
    VariableSpec("big_vs_weak_signal", "Segnale big vs weak", "match_dynamics", "diagnostic_only", "trace.big_vs_weak_signal"),
    VariableSpec("boost_applied", "Boost applicato", "match_dynamics", "diagnostic_only", "trace.boost_applied"),
    VariableSpec("league_blend_applied", "League blend", "match_dynamics", "diagnostic_only", "trace.league_blend_applied"),
    VariableSpec("data_quality_score", "Qualità dati", "data_quality", "diagnostic_only", "features.data_quality"),
)

VARIABLE_REGISTRY: dict[str, VariableSpec] = {
    v.key: v
    for v in (*BASE_VARIABLES, *CONTEXT_VARIABLES, *MATCH_LEVEL_VARIABLES)
}

BASE_KEYS_IN_MODEL: frozenset[str] = frozenset(
    {
        "avg_sot_for",
        "opponent_conceded_sot_avg",
        "last5_avg_sot_for",
        "home_away_split_sot_for",
        "xg_to_sot",
        "shots_to_sot",
    }
)


def get_variable_spec(key: str) -> VariableSpec | None:
    return VARIABLE_REGISTRY.get(key)
