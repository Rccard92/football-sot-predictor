"""
Manifest variabili applicate per model_version (fonte di verità tracciabilità Framework ↔ Debug).
Solo metadati: nessun calcolo predittivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
)

ApplicationRole = Literal[
    "direct_formula_component",
    "component_input",
    "context_risk",
    "quality_control",
    "debug_only",
    "not_available",
]

COUNTABLE_APPLICATION_ROLES: frozenset[str] = frozenset(
    {
        "direct_formula_component",
        "component_input",
        "context_risk",
        "quality_control",
    },
)


@dataclass(frozen=True)
class AppliedVariableSpec:
    """Una voce del manifest: cosa deve comparire nel trace / debug per il modello."""

    trace_key: str
    label: str
    area: str
    application_role: ApplicationRole
    parent_component: str | None
    direct_formula_impact: bool
    expected_in_debug: bool
    # Chiave variabile nel Framework Analisi (campo `key`), se allineabile
    framework_key: str | None = None
    # Discriminante per il builder trace (stringa compatta)
    resolver: str = ""


def is_countable_role(role: str) -> bool:
    return role in COUNTABLE_APPLICATION_ROLES


def manifest_for_model(model_version: str) -> list[AppliedVariableSpec]:
    if model_version == BASELINE_SOT_MODEL_VERSION:
        return _MANIFEST_V01
    if model_version == BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT:
        return _MANIFEST_V03
    if model_version == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
        return _MANIFEST_V04
    if model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT:
        return list(_MANIFEST_V10)
    if model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT:
        return list(_MANIFEST_V11)
    if model_version in (BASELINE_SOT_MODEL_VERSION_V02, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED):
        return _MANIFEST_V02
    return []


def manifest_index_by_framework_key(model_version: str) -> dict[str, list[AppliedVariableSpec]]:
    out: dict[str, list[AppliedVariableSpec]] = {}
    for spec in manifest_for_model(model_version):
        if spec.framework_key:
            out.setdefault(spec.framework_key, []).append(spec)
    return out


def all_manifest_framework_keys_union() -> dict[str, list[AppliedVariableSpec]]:
    """Indice globale framework_key → specs (tutte le versioni)."""
    acc: dict[str, list[AppliedVariableSpec]] = {}
    for mv in (
        BASELINE_SOT_MODEL_VERSION,
        BASELINE_SOT_MODEL_VERSION_V02,
        BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
        BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V10_SOT,
        BASELINE_SOT_MODEL_VERSION_V11_SOT,
    ):
        for spec in manifest_for_model(mv):
            if spec.framework_key:
                acc.setdefault(spec.framework_key, []).append(spec)
    return acc


_MODEL_PRIORITY: tuple[str, ...] = (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION,
)


def model_versions_declaring_framework_key(framework_key: str) -> list[str]:
    out: list[str] = []
    for mv in _MODEL_PRIORITY:
        if any(s.framework_key == framework_key for s in manifest_for_model(mv)):
            out.append(mv)
    return out


def enrich_framework_areas(areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggiorna dict variabili con application_role / applied_now derivati dal manifest."""
    for area in areas:
        vars_ = area.get("variables")
        if not isinstance(vars_, list):
            continue
        for var in vars_:
            if not isinstance(var, dict):
                continue
            key = str(var.get("key") or "")
            chosen: AppliedVariableSpec | None = None
            for mv in _MODEL_PRIORITY:
                for spec in manifest_for_model(mv):
                    if spec.framework_key == key:
                        chosen = spec
                        break
                if chosen is not None:
                    break
            if chosen is None:
                var["application_role"] = "debug_only"
                var["parent_component"] = None
                var["expected_in_debug"] = False
                var["applied_to_model_versions"] = []
                var["applied_now"] = False
                continue
            var["application_role"] = chosen.application_role
            var["parent_component"] = chosen.parent_component
            var["expected_in_debug"] = chosen.expected_in_debug
            var["direct_formula_impact"] = chosen.direct_formula_impact
            var["applied_to_model_versions"] = model_versions_declaring_framework_key(key)
            var["applied_now"] = is_countable_role(str(chosen.application_role))
    return areas


# --- v0.1: 6 fattori pesati + confidence ---
_V01_FACTORS: list[tuple[str, str, str]] = [
    ("season_avg_sot_for", "Media stagionale tiri in porta fatti", "Produzione / baseline"),
    ("opponent_season_avg_sot_conceded", "Media stagionale tiri in porta concessi all'avversario", "Avversario / baseline"),
    ("home_away_avg_sot_for", "Media tiri in porta fatti in casa o in trasferta", "Contesto casa/trasferta"),
    ("opponent_home_away_avg_sot_conceded", "Tiri in porta concessi dall'avversario in casa/trasferta", "Avversario / split"),
    ("last5_avg_sot_for", "Forma recente: media SOT fatti", "Forma recente"),
    ("opponent_last5_avg_sot_conceded", "Forma recente: SOT concessi dall'avversario", "Forma recente"),
]

_MANIFEST_V01: list[AppliedVariableSpec] = [
    AppliedVariableSpec(
        trace_key=f"v01_factor_{k}",
        label=lab,
        area=area,
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=k,
        resolver=f"v01_factor:{k}",
    )
    for k, lab, area in _V01_FACTORS
] + [
    AppliedVariableSpec(
        trace_key="v01_prediction_confidence",
        label="Confidence previsione (score)",
        area="Qualità dati",
        application_role="quality_control",
        parent_component=None,
        direct_formula_impact=False,
        expected_in_debug=True,
        framework_key="prediction_confidence",
        resolver="v01_quality:confidence_score",
    ),
]


# --- v0.2: baseline + 4 adjustment + confidence v02 ---
_MANIFEST_V02: list[AppliedVariableSpec] = [
    AppliedVariableSpec(
        trace_key="v02_baseline_expected_sot",
        label="Baseline v0.1 di partenza",
        area="Formula v0.2",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v02:baseline",
    ),
    AppliedVariableSpec(
        trace_key="v02_adj_player",
        label="Aggiustamento profilo giocatori",
        area="Player impact",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v02:adjustment:player",
    ),
    AppliedVariableSpec(
        trace_key="v02_adj_h2h",
        label="Aggiustamento H2H",
        area="Confronti diretti",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v02:adjustment:h2h",
    ),
    AppliedVariableSpec(
        trace_key="v02_adj_motivation",
        label="Aggiustamento motivazione / contesto",
        area="Contesto match",
        application_role="context_risk",
        parent_component=None,
        direct_formula_impact=False,
        expected_in_debug=True,
        framework_key=None,
        resolver="v02:adjustment:motivation",
    ),
    AppliedVariableSpec(
        trace_key="v02_adj_availability",
        label="Aggiustamento disponibilità",
        area="Disponibilità",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v02:adjustment:availability",
    ),
    AppliedVariableSpec(
        trace_key="v02_prediction_confidence",
        label="Confidence previsione v0.2",
        area="Qualità dati",
        application_role="quality_control",
        parent_component=None,
        direct_formula_impact=False,
        expected_in_debug=True,
        framework_key=None,
        resolver="v02:quality:confidence_v02",
    ),
]


# --- v0.3: 5 componenti + input per componente (chiavi raw inputs/resolved) ---
_V03_COMPONENT_ROWS: list[tuple[str, str, str]] = [
    ("core_sot_component", "Core SOT diretto", "core_sot_component"),
    ("shot_volume_component", "Volume tiri", "shot_volume_component"),
    ("shot_accuracy_component", "Precisione tiro", "shot_accuracy_component"),
    ("recent_form_component", "Forma recente", "recent_form_component"),
    ("goals_context_component", "Goal context", "goals_context_component"),
]

_V03_INPUTS_BY_COMP: dict[str, list[tuple[str, str]]] = {
    "core_sot_component": [
        ("season_avg_sot_for", "Media stagionale SOT fatti"),
        ("opponent_season_avg_sot_conceded", "Media stagionale SOT concessi avversario"),
        ("split_avg_sot_for", "Media SOT fatti split casa/trasferta"),
        ("opponent_split_avg_sot_conceded", "Media SOT concessi avversario split"),
    ],
    "shot_volume_component": [
        ("season_avg_shots_for", "Media tiri totali fatti"),
        ("opponent_season_avg_shots_conceded", "Media tiri concessi avversario"),
        ("split_avg_shots_for", "Media tiri fatti split"),
        ("opponent_split_avg_shots_conceded", "Media tiri concessi split"),
    ],
    "shot_accuracy_component": [
        ("shot_accuracy_for", "Precisione tiro (SOT/tiri)"),
        ("opponent_sot_allowed_ratio", "Rapporto SOT concessi/tiri subiti avversario"),
    ],
    "recent_form_component": [
        ("last5_avg_sot_for", "SOT fatti ultime 5"),
        ("opponent_last5_avg_sot_conceded", "SOT concessi avversario ultime 5"),
        ("last10_avg_sot_for", "SOT fatti ultime 10"),
        ("opponent_last10_avg_sot_conceded", "SOT concessi avversario ultime 10"),
    ],
    "goals_context_component": [
        ("season_avg_goals_for", "Media goal fatti"),
        ("opponent_season_avg_goals_conceded", "Media goal concessi avversario"),
    ],
}

_MANIFEST_V03: list[AppliedVariableSpec] = []
for _tid, _lab, comp_key in _V03_COMPONENT_ROWS:
    _MANIFEST_V03.append(
        AppliedVariableSpec(
            trace_key=f"v03_component_{comp_key}",
            label=_lab,
            area="Mix v0.3",
            application_role="direct_formula_component",
            parent_component=None,
            direct_formula_impact=True,
            expected_in_debug=True,
            framework_key=comp_key,
            resolver=f"v03:component:{comp_key}",
        )
    )
for comp_key, rows in _V03_INPUTS_BY_COMP.items():
    for inp_key, inp_lab in rows:
        _MANIFEST_V03.append(
            AppliedVariableSpec(
                trace_key=f"v03_input_{comp_key}_{inp_key}",
                label=inp_lab,
                area="Input componente v0.3",
                application_role="component_input",
                parent_component=comp_key,
                direct_formula_impact=False,
                expected_in_debug=True,
                framework_key=inp_key,
                resolver=f"v03:input:{comp_key}:{inp_key}",
            )
        )
_MANIFEST_V03.append(
    AppliedVariableSpec(
        trace_key="v03_team_priors_matches_count",
        label="Conteggio partite priors squadra (meta)",
        area="Qualità dati",
        application_role="quality_control",
        parent_component=None,
        direct_formula_impact=False,
        expected_in_debug=True,
        framework_key=None,
        resolver="v03:quality:team_priors_matches_count",
    )
)


_V10_FORMULA_TERMS: list[tuple[str, str, str | None]] = [
    ("offensive_production_component", "Produzione offensiva composita", None),
    ("opp_avg_sot_conceded", "Tiri in porta concessi dall'avversario (stagione)", "avg_sot_conceded"),
    ("team_split_avg_sot_for", "SOT fatti in split casa/trasferta", None),
    ("opp_split_avg_sot_conceded", "SOT concessi avversario in split", None),
    ("team_last5_avg_sot_for", "SOT fatti ultime 5", None),
    ("opp_last5_avg_sot_conceded", "SOT concessi avversario ultime 5", None),
]

_V10_OFFENSIVE_INPUTS: list[tuple[str, str, str]] = [
    ("avg_sot_for", "Media tiri in porta fatti", "avg_sot_for"),
    ("avg_total_shots_for", "Media tiri totali fatti", "avg_shots_for"),
    ("shot_accuracy_for", "Precisione tiro", "conv_shots_to_sot"),
    ("avg_inside_box_shots_for", "Media tiri dentro area", "avg_box_shots_for"),
    ("avg_outside_box_shots_for", "Media tiri fuori area", "avg_outbox_shots_for"),
    ("avg_blocked_shots_for", "Media tiri bloccati", "avg_blocked_shots_for"),
    ("avg_shots_off_goal_for", "Media tiri fuori dallo specchio", "avg_shots_off_goal_for"),
    ("avg_goals_for", "Media goal fatti", "avg_goals_for"),
    ("offensive_trend", "Trend offensivo recente", "offensive_trend"),
]

_MANIFEST_V10: list[AppliedVariableSpec] = []
for trace_k, lab, fwk in _V10_FORMULA_TERMS:
    _MANIFEST_V10.append(
        AppliedVariableSpec(
            trace_key=f"v10_term_{trace_k}",
            label=lab,
            area="Formula finale v1.0",
            application_role="direct_formula_component",
            parent_component=None,
            direct_formula_impact=True,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v10:formula_term:{trace_k}",
        )
    )
for inp_k, lab, fwk in _V10_OFFENSIVE_INPUTS:
    _MANIFEST_V10.append(
        AppliedVariableSpec(
            trace_key=f"v10_off_input_{inp_k}",
            label=lab,
            area="Produzione offensiva composita",
            application_role="component_input",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v10:offensive_input:{inp_k}",
        )
    )
_MANIFEST_V10.append(
    AppliedVariableSpec(
        trace_key="v10_expected_goals",
        label="xG / Expected goals",
        area="Qualità occasioni",
        application_role="direct_formula_component",
        parent_component="xg_quality_component",
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key="expected_goals",
        resolver="v10:xg_component:expected_goals",
    )
)
_MANIFEST_V10.extend(
    [
        AppliedVariableSpec(
            trace_key="v10_offensive_quality",
            label="Qualità input componente offensiva",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v10:quality:offensive_component",
        ),
        AppliedVariableSpec(
            trace_key="v10_ctx_kickoff_timedelta",
            label="Distanza temporale dal calcio d'inizio",
            area="Contesto match",
            application_role="context_risk",
            parent_component=None,
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key="tempo_al_kickoff",
            resolver="fixture:hours_to_kickoff",
        ),
    ]
)

_MANIFEST_V10_EXPECTED_GOALS = AppliedVariableSpec(
    trace_key="v10_expected_goals",
    label="xG / Expected goals",
    area="Qualità occasioni",
    application_role="direct_formula_component",
    parent_component="xg_quality_component",
    direct_formula_impact=True,
    expected_in_debug=True,
    framework_key="expected_goals",
    resolver="v10:xg_component:expected_goals",
)


_V11_OFFENSIVE_INPUTS: list[tuple[str, str, str]] = [
    ("avg_sot_for", "Media tiri in porta fatti", "avg_sot_for"),
    ("avg_total_shots_for", "Media tiri totali fatti", "avg_shots_for"),
    ("shot_accuracy_for", "Precisione tiro", "conv_shots_to_sot"),
    ("avg_inside_box_shots_for", "Media tiri dentro area", "avg_box_shots_for"),
    ("avg_outside_box_shots_for", "Media tiri fuori area", "avg_outbox_shots_for"),
    ("avg_blocked_shots_for", "Media tiri bloccati", "avg_blocked_shots_for"),
    ("avg_shots_off_goal_for", "Media tiri fuori dallo specchio", "avg_shots_off_goal_for"),
    ("avg_goals_for", "Media goal fatti", "avg_goals_for"),
    ("offensive_trend", "Trend offensivo recente", "offensive_trend"),
]

_V11_DEFENSIVE_INPUTS: list[tuple[str, str, str]] = [
    ("opponent_avg_sot_conceded", "SOT concessi avversario stagione", "avg_sot_conceded"),
    ("opponent_avg_total_shots_conceded", "Tiri totali concessi avversario", "avg_shots_conceded"),
    (
        "opponent_avg_inside_box_shots_conceded",
        "Tiri dentro area concessi avversario",
        "avg_box_shots_conceded",
    ),
    (
        "opponent_avg_outside_box_shots_conceded",
        "Tiri fuori area concessi avversario",
        "avg_outbox_shots_conceded",
    ),
    ("opponent_avg_blocked_shots_conceded", "Tiri bloccati concessi avversario", "avg_blocked_shots_conceded"),
    ("opponent_defensive_trend_recent", "Trend difensivo recente avversario", "defensive_trend"),
]

_V11_SPLIT_INPUTS: list[tuple[str, str, str]] = [
    ("split_avg_sot_for", "SOT fatti casa/fuori", "split_avg_sot_for"),
    ("split_opponent_avg_sot_conceded", "SOT concessi avversario casa/fuori", "split_avg_sot_conceded"),
    ("split_avg_total_shots_for", "Tiri totali fatti casa/fuori", "split_avg_shots_for"),
    (
        "split_opponent_avg_total_shots_conceded",
        "Tiri totali concessi avversario casa/fuori",
        "split_avg_shots_conceded",
    ),
    ("home_away_performance_delta", "Differenza rendimento casa/fuori", "home_away_delta"),
]

_V11_RECENT_INPUTS: list[tuple[str, str, str]] = [
    ("recent_avg_sot_for", "SOT fatti ultime 5", "recent_avg_sot_for"),
    (
        "recent_opponent_avg_sot_conceded",
        "SOT concessi avversario ultime 5",
        "recent_opponent_avg_sot_conceded",
    ),
    ("recent_avg_total_shots_for", "Tiri totali fatti ultime 5", "recent_avg_total_shots_for"),
    (
        "recent_opponent_avg_total_shots_conceded",
        "Tiri totali concessi avversario ultime 5",
        "recent_opponent_avg_total_shots_conceded",
    ),
    ("recent_avg_goals_for", "Goal fatti ultime 5", "recent_avg_goals_for"),
    ("recent_trend_vs_season", "Trend rispetto alla media stagionale", "recent_trend_vs_season"),
]

_V11_PLAYER_INPUTS: list[tuple[str, str, str]] = [
    ("top_players_sot_per90_signal", "Tiri in porta per 90 dei top player", "top_players_sot_per90_signal"),
    ("top_players_shots_per90_signal", "Tiri totali per 90 dei top player", "top_players_shots_per90_signal"),
    ("top_players_sot_share_signal", "Quota SOT squadra top player", "top_players_sot_share_signal"),
    ("top_players_shots_share_signal", "Quota tiri squadra top player", "top_players_shots_share_signal"),
    ("top_players_recent_minutes_signal", "Minuti recenti top player", "top_players_recent_minutes_signal"),
    ("top_players_rating_signal", "Rating medio top player", "top_players_rating_signal"),
    ("top_players_reliability_signal", "Affidabilità profili top player", "top_players_reliability_signal"),
]

_V11_XG_INPUTS: list[tuple[str, str, str]] = [
    ("avg_xg_for", "xG prodotti", "avg_xg_for"),
    ("opponent_avg_xg_conceded", "xG concessi dall'avversario", "opponent_avg_xg_conceded"),
    ("team_xg_delta_vs_league", "Delta xG squadra vs media lega", "team_xg_delta_vs_league"),
    (
        "opponent_xg_conceded_delta_vs_league",
        "Delta xG concesso avversario vs media lega",
        "opponent_xg_conceded_delta_vs_league",
    ),
    ("xg_prudent_adjustment_signal", "xG adjustment prudente", "xg_prudent_adjustment_signal"),
]

_MANIFEST_V11: list[AppliedVariableSpec] = [
    AppliedVariableSpec(
        trace_key="v11_term_offensive_production_component",
        label="Produzione offensiva composita",
        area="Formula finale v1.1",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v11:formula_term:offensive_production_component",
    ),
    AppliedVariableSpec(
        trace_key="v11_term_opponent_defensive_resistance_component",
        label="Resistenza difensiva avversaria",
        area="Formula finale v1.1",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v11:formula_term:opponent_defensive_resistance_component",
    ),
    AppliedVariableSpec(
        trace_key="v11_term_home_away_split_component",
        label="Split casa/trasferta",
        area="Formula finale v1.1",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v11:formula_term:home_away_split_component",
    ),
    AppliedVariableSpec(
        trace_key="v11_term_recent_form_component",
        label="Forma recente",
        area="Formula finale v1.1",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v11:formula_term:recent_form_component",
    ),
    AppliedVariableSpec(
        trace_key="v11_term_xg_chance_quality_component",
        label="Qualità occasioni / xG",
        area="Formula finale v1.1",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v11:formula_term:xg_chance_quality_component",
    ),
    AppliedVariableSpec(
        trace_key="v11_term_player_layer_component",
        label="Player layer / Impatto giocatori",
        area="Formula finale v1.1",
        application_role="direct_formula_component",
        parent_component=None,
        direct_formula_impact=True,
        expected_in_debug=True,
        framework_key=None,
        resolver="v11:formula_term:player_layer_component",
    ),
]
for inp_k, lab, fwk in _V11_OFFENSIVE_INPUTS:
    _MANIFEST_V11.append(
        AppliedVariableSpec(
            trace_key=f"v11_off_input_{inp_k}",
            label=lab,
            area="Produzione offensiva composita",
            application_role="component_input",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v11:offensive_input:{inp_k}",
        ),
    )
for inp_k, lab, fwk in _V11_DEFENSIVE_INPUTS:
    _MANIFEST_V11.append(
        AppliedVariableSpec(
            trace_key=f"v11_def_input_{inp_k}",
            label=lab,
            area="Resistenza difensiva avversaria",
            application_role="component_input",
            parent_component="opponent_defensive_resistance_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v11:defensive_input:{inp_k}",
        ),
    )
for inp_k, lab, fwk in _V11_SPLIT_INPUTS:
    _MANIFEST_V11.append(
        AppliedVariableSpec(
            trace_key=f"v11_split_input_{inp_k}",
            label=lab,
            area="Split casa/trasferta",
            application_role="component_input",
            parent_component="home_away_split_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v11:split_input:{inp_k}",
        ),
    )
for inp_k, lab, fwk in _V11_RECENT_INPUTS:
    _MANIFEST_V11.append(
        AppliedVariableSpec(
            trace_key=f"v11_recent_input_{inp_k}",
            label=lab,
            area="Forma recente",
            application_role="component_input",
            parent_component="recent_form_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v11:recent_input:{inp_k}",
        ),
    )
for inp_k, lab, fwk in _V11_XG_INPUTS:
    _MANIFEST_V11.append(
        AppliedVariableSpec(
            trace_key=f"v11_xg_input_{inp_k}",
            label=lab,
            area="Qualità occasioni / xG",
            application_role="component_input",
            parent_component="xg_chance_quality_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v11:xg_input:{inp_k}",
        ),
    )
for inp_k, lab, fwk in _V11_PLAYER_INPUTS:
    _MANIFEST_V11.append(
        AppliedVariableSpec(
            trace_key=f"v11_player_input_{inp_k}",
            label=lab,
            area="Player layer / Impatto giocatori",
            application_role="component_input",
            parent_component="player_layer_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v11:player_input:{inp_k}",
        ),
    )
_MANIFEST_V11.extend(
    [
        AppliedVariableSpec(
            trace_key="v11_offensive_quality",
            label="Qualità input componente offensiva",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v11:quality:offensive_component",
        ),
        AppliedVariableSpec(
            trace_key="v11_defensive_quality",
            label="Qualità input componente difensiva avversaria",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="opponent_defensive_resistance_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v11:quality:defensive_component",
        ),
        AppliedVariableSpec(
            trace_key="v11_split_quality",
            label="Qualità input componente split casa/trasferta",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="home_away_split_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v11:quality:split_component",
        ),
        AppliedVariableSpec(
            trace_key="v11_recent_quality",
            label="Qualità input componente forma recente",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="recent_form_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v11:quality:recent_component",
        ),
        AppliedVariableSpec(
            trace_key="v11_xg_quality",
            label="Qualità input componente xG",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="xg_chance_quality_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v11:quality:xg_component",
        ),
        AppliedVariableSpec(
            trace_key="v11_player_quality",
            label="Qualità input componente player layer",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="player_layer_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v11:quality:player_component",
        ),
        AppliedVariableSpec(
            trace_key="v11_ctx_top_shooter_presence",
            label="Presenza top shooter titolari",
            area="Player layer / contesto",
            application_role="component_input",
            parent_component="player_layer_component",
            direct_formula_impact=True,
            expected_in_debug=True,
            framework_key="top_shooter_presence",
            resolver="v11:ctx:top_shooter_presence",
        ),
        AppliedVariableSpec(
            trace_key="v11_ctx_top_shooter_absence",
            label="Top shooter non titolari / non in distinta",
            area="Player layer / contesto",
            application_role="component_input",
            parent_component="player_layer_component",
            direct_formula_impact=True,
            expected_in_debug=True,
            framework_key="top_shooter_absence",
            resolver="v11:ctx:top_shooter_absence",
        ),
        AppliedVariableSpec(
            trace_key="v11_ctx_kickoff_timedelta",
            label="Distanza temporale dal calcio d'inizio",
            area="Contesto match",
            application_role="context_risk",
            parent_component=None,
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key="tempo_al_kickoff",
            resolver="fixture:hours_to_kickoff",
        ),
    ],
)


# --- v0.4: 6 termini formula + input offensivi + qualità ---
_V04_OFF_KEYS: list[tuple[str, str, str]] = [
    ("avg_sot_for", "Media tiri in porta fatti", "avg_sot_for"),
    ("avg_total_shots_for", "Media tiri totali fatti", "avg_shots_for"),
    ("avg_inside_box_shots_for", "Media tiri dentro area", "avg_box_shots_for"),
    ("avg_outside_box_shots_for", "Media tiri fuori area", "avg_outbox_shots_for"),
    ("shot_accuracy_for", "Precisione di tiro (SOT / tiri)", "conv_shots_to_sot"),
    ("avg_goals_for", "Media goal fatti", "avg_goals_for"),
    ("offensive_trend", "Trend offensivo (ultime vs stagione)", "offensive_trend"),
]

_V04_BASELINE_TERMS: list[tuple[str, str, str | None]] = [
    ("offensive_production_component", "Produzione offensiva (componente)", None),
    ("opp_avg_sot_conceded", "Tiri in porta concessi dall'avversario (stagione)", "avg_sot_conceded"),
    ("team_split_avg_sot_for", "SOT fatti in split casa/trasferta", None),
    ("opp_split_avg_sot_conceded", "SOT concessi avversario in split", None),
    ("team_last5_avg_sot_for", "SOT fatti ultime 5", None),
    ("opp_last5_avg_sot_conceded", "SOT concessi avversario ultime 5", None),
]

_MANIFEST_V04: list[AppliedVariableSpec] = []
for trace_k, lab, fwk in _V04_BASELINE_TERMS:
    _MANIFEST_V04.append(
        AppliedVariableSpec(
            trace_key=f"v04_term_{trace_k}",
            label=lab,
            area="Formula finale v0.4",
            application_role="direct_formula_component",
            parent_component=None,
            direct_formula_impact=True,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v04:formula_term:{trace_k}",
        )
    )
for inp_k, lab, fwk in _V04_OFF_KEYS:
    _MANIFEST_V04.append(
        AppliedVariableSpec(
            trace_key=f"v04_off_input_{inp_k}",
            label=lab,
            area="Produzione offensiva squadra",
            application_role="component_input",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=fwk,
            resolver=f"v04:offensive_input:{inp_k}",
        )
    )
_MANIFEST_V04.extend(
    [
        AppliedVariableSpec(
            trace_key="v04_offensive_cap",
            label="Cap sulla componente offensiva",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v04:quality:cap",
        ),
        AppliedVariableSpec(
            trace_key="v04_offensive_fallbacks",
            label="Fallback componente offensiva (elenco)",
            area="Qualità dati",
            application_role="quality_control",
            parent_component="offensive_production_component",
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key=None,
            resolver="v04:quality:fallbacks",
        ),
        AppliedVariableSpec(
            trace_key="v04_prediction_confidence",
            label="Confidence previsione (riga prediction)",
            area="Qualità dati",
            application_role="quality_control",
            parent_component=None,
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key="prediction_confidence",
            resolver="v04:quality:row_confidence",
        ),
        AppliedVariableSpec(
            trace_key="v04_ctx_standings",
            label="Classifica / contesto standings (audit)",
            area="Contesto match",
            application_role="context_risk",
            parent_component=None,
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key="classifica_attuale",
            resolver="audit:standings_context",
        ),
        AppliedVariableSpec(
            trace_key="v04_ctx_season_phase",
            label="Fase stagione (audit)",
            area="Contesto match",
            application_role="context_risk",
            parent_component=None,
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key="fase_stagione",
            resolver="audit:season_phase_context",
        ),
        AppliedVariableSpec(
            trace_key="v04_ctx_kickoff_timedelta",
            label="Distanza temporale dal calcio d'inizio",
            area="Contesto match",
            application_role="context_risk",
            parent_component=None,
            direct_formula_impact=False,
            expected_in_debug=True,
            framework_key="tempo_al_kickoff",
            resolver="fixture:hours_to_kickoff",
        ),
    ]
)
