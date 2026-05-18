"""
Lettura-only: assembla la spiegazione di una previsione SOT da dati già persistiti
(team_sot_predictions, fixtures, audit variabili per campioni partite).
Non ricalcola formule né modifica prediction.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    FINISHED_STATUSES,
)
from app.models import Fixture, Season, Team, TeamSotPrediction
from app.schemas.match_analysis import MatchVariablesAuditResponse
from app.services.debug_sot_model_comparison import build_model_comparison_for_fixture
from app.services.match_variable_audit_service import MatchVariableAuditService
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import (
    build_applied_variable_trace_side,
    compute_hours_to_kickoff,
    validate_model_trace,
)
from app.services.predictions_v10.offensive_production_blend import offensive_inputs_as_map
from app.services.predictions_v11.player_layer_feature_sources import COMPONENT_KEY_PLAYER, COMPONENT_LABEL_PLAYER
from app.services.predictions_v11.xg_feature_sources import COMPONENT_KEY_XG, COMPONENT_LABEL_XG
from app.services.sot_feature_registry import (
    V11_FORMULA_DEFENSIVE_WEIGHT,
    V11_FORMULA_OFFENSIVE_WEIGHT,
    V11_FORMULA_PLAYER_WEIGHT,
    V11_FORMULA_RECENT_WEIGHT,
    V11_FORMULA_SPLIT_WEIGHT,
    V11_FORMULA_XG_WEIGHT,
)
from app.services.sot_model_constants import WEIGHTS_BASELINE_V0_1

logger = logging.getLogger(__name__)

Side = Literal["home", "away"]

V01_LABELS: dict[str, str] = {
    "season_avg_sot_for": "Media stagionale tiri in porta fatti",
    "opponent_season_avg_sot_conceded": "Media stagionale tiri in porta concessi all'avversario",
    "home_away_avg_sot_for": "Media tiri in porta fatti in casa o in trasferta",
    "opponent_home_away_avg_sot_conceded": "Tiri in porta concessi dall'avversario in casa/trasferta",
    "last5_avg_sot_for": "Forma recente: media SOT fatti (ultime partite)",
    "opponent_last5_avg_sot_conceded": "Forma recente: SOT concessi dall'avversario",
}

V04_OFFENSIVE_INPUT_LABELS: dict[str, str] = {
    "avg_sot_for": "Media tiri in porta fatti (stagione)",
    "avg_total_shots_for": "Media tiri totali fatti",
    "avg_inside_box_shots_for": "Media tiri dentro l'area",
    "avg_outside_box_shots_for": "Media tiri fuori area",
    "shot_accuracy_for": "Precisione di tiro (SOT / tiri)",
    "avg_goals_for": "Media goal fatti",
    "offensive_trend": "Trend offensivo (ultime vs stagione)",
}

V04_BASELINE_KEYS_ORDER: list[tuple[str, str, float]] = [
    ("offensive_signal", "Componente offensiva (core v0.4)", 0.30),
    ("opp_avg_sot_conceded", "Tiri in porta concessi dall'avversario (stagione)", 0.25),
    ("team_split_avg_sot_for", "SOT fatti in split casa/trasferta", 0.15),
    ("opp_split_avg_sot_conceded", "SOT concessi dall'avversario in split", 0.10),
    ("team_last5_avg_sot_for", "SOT fatti ultime 5", 0.10),
    ("opp_last5_avg_sot_conceded", "SOT concessi avversario ultime 5", 0.10),
]

V03_COMPONENT_META: list[tuple[str, str, str, float]] = [
    ("core_sot_component", "Core SOT diretto", "core_sot_component", 0.55),
    ("shot_volume_component", "Volume tiri", "shot_volume_component", 0.20),
    ("shot_accuracy_component", "Precisione tiro", "shot_accuracy_component", 0.10),
    ("recent_form_component", "Forma recente", "recent_form_component", 0.10),
    ("goals_context_component", "Goal context", "goals_context_component", 0.05),
]

# Chiavi audit (team_sot) ↔ input salvati nel componente offensivo v0.4
V04_INPUT_TO_AUDIT_KEY: dict[str, str] = {
    "avg_sot_for": "season_avg_sot_for",
    "avg_total_shots_for": "season_avg_shots_for",
    "avg_goals_for": "season_avg_goals_for",
    "shot_accuracy_for": "shot_accuracy_for",
    "offensive_trend": "trend_last5_vs_season_sot_for",
}

COMPARE_MODELS_ORDER: list[tuple[str, str]] = [
    (BASELINE_SOT_MODEL_VERSION, "v0.1"),
    (BASELINE_SOT_MODEL_VERSION_V02, "v0.2"),
    (BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED, "v0.2 player"),
    (BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, "v0.3"),
    (BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, "v0.4"),
    (BASELINE_SOT_MODEL_VERSION_V11_SOT, "v1.1"),
    (BASELINE_SOT_MODEL_VERSION_V10_SOT, "v1.0"),
]

UI_COMPARE_MODEL_VERSIONS: frozenset[str] = frozenset(
    {
        BASELINE_SOT_MODEL_VERSION_V11_SOT,
        BASELINE_SOT_MODEL_VERSION_V10_SOT,
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    },
)

CHECKSUM_TOLERANCE = 0.02
CHECKSUM_WARNING_IT = (
    "La somma dei contributi non coincide perfettamente con la prediction salvata. "
    "Possibili arrotondamenti, cap o fallback."
)

V11_BLOCKED_OFF_DIAG_KEYS = frozenset({"avg_blocked_shots_for", "avg_shots_off_goal_for"})

V03_INCLUDES_BY_COMP: dict[str, list[str]] = {
    "core_sot_component": [
        "season_avg_sot_for",
        "opponent_season_avg_sot_conceded",
        "split_avg_sot_for",
        "opponent_split_avg_sot_conceded",
    ],
    "shot_volume_component": [
        "season_avg_shots_for",
        "opponent_season_avg_shots_conceded",
        "split_avg_shots_for",
        "opponent_split_avg_shots_conceded",
    ],
    "shot_accuracy_component": ["shot_accuracy_for", "opponent_sot_allowed_ratio"],
    "recent_form_component": [
        "last5_avg_sot_for",
        "opponent_last5_avg_sot_conceded",
        "last10_avg_sot_for",
        "opponent_last10_avg_sot_conceded",
    ],
    "goals_context_component": ["season_avg_goals_for", "opponent_season_avg_goals_conceded"],
}


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _finished(status: str | None) -> bool:
    return (status or "").upper() in FINISHED_STATUSES


def _outcome_sot(abs_err: float | None) -> str | None:
    if abs_err is None:
        return None
    e = float(abs_err)
    if e <= 0.25:
        return "Centrata"
    if e <= 0.75:
        return "Vicina"
    if e <= 1.25:
        return "Da controllare"
    return "Errata"


def _post_audit_judgment(abs_err: float | None) -> str | None:
    if abs_err is None:
        return None
    e = float(abs_err)
    if e <= 0.50:
        return "Ottima"
    if e <= 1.00:
        return "Vicina"
    if e <= 1.50:
        return "Accettabile"
    return "Da analizzare"


def _direction_label(value: float | None, predicted: float) -> str:
    if value is None:
        return "neutro"
    if value >= predicted + 0.35:
        return "aumenta"
    if value <= predicted - 0.35:
        return "riduce"
    return "neutro"


def _active_model_version_from_preds(
    preds: dict[str, dict[str, float | None]],
) -> str | None:
    from app.services.model_version_preference import resolve_active_model_for_fixture_preds

    return resolve_active_model_for_fixture_preds(preds)


def _components_v01(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    weights = raw.get("weights")
    resolved = raw.get("resolved_inputs")
    inputs = raw.get("inputs")
    if not isinstance(weights, dict) or not isinstance(resolved, dict):
        return []
    variables: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for key, w_def in WEIGHTS_BASELINE_V0_1.items():
        w = _safe_float(weights.get(key, w_def))
        val = _safe_float(resolved.get(key))
        if w is None or val is None:
            continue
        contrib = round(float(val) * float(w), 4)
        raw_in = inputs.get(key) if isinstance(inputs, dict) else None
        fb = raw_in is None
        variables.append(
            {
                "key": key,
                "label": V01_LABELS.get(key, key),
                "value": _round2(val),
                "unit": "tiri in porta",
                "weight_internal": w,
                "contribution": contrib,
                "formula": f"resolved({key}) × {w}",
                "data_source": "team_sot_predictions.raw_json (baseline v0.1)",
                "matches_count": None,
                "sum": None,
                "sample_rows_count": None,
                "fallback_used": fb,
                "cap_applied": False,
                "no_data_leakage_note": "Sì (valori da feature pre-match salvati nella prediction)",
                "sample_matches": [],
                "sample_matches_note": None,
                "status": "missing" if fb else "available",
            },
        )
        out.append(
            {
                "id": f"v01_{key}",
                "label": V01_LABELS.get(key, key),
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "direction": _direction_label(val, predicted),
                "data_status": "fallback" if fb else "ok",
                "notes": "Input grezzo assente: usato valore risolto." if fb else None,
                "variables": [variables[-1]],
            },
        )
    return out


def _components_v03(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    comps = raw.get("components")
    wmap = raw.get("weights")
    if not isinstance(comps, dict) or not isinstance(wmap, dict):
        return []
    out: list[dict[str, Any]] = []
    for comp_id, label_it, comp_key, w_def in V03_COMPONENT_META:
        w = _safe_float(wmap.get(comp_key))
        if w is None:
            w = w_def
        cobj = comps.get(comp_key) if isinstance(comps, dict) else None
        val = _safe_float((cobj or {}).get("value")) if isinstance(cobj, dict) else None
        if val is None:
            continue
        contrib = round(float(val) * float(w), 4)
        formula = str((cobj or {}).get("formula") or f"component {comp_key}")
        var_row = {
            "key": comp_key,
            "label": label_it,
            "value": _round2(val),
            "unit": "tiri in porta (scala componente)",
            "weight_internal": w,
            "contribution": contrib,
            "formula": formula,
            "data_source": "team_sot_predictions.raw_json (v0.3)",
            "matches_count": (raw.get("meta") or {}).get("team_priors_matches_count")
            if isinstance(raw.get("meta"), dict)
            else None,
            "sum": None,
            "sample_rows_count": None,
            "fallback_used": False,
            "cap_applied": False,
            "no_data_leakage_note": "Sì (snapshot salvato)",
            "sample_matches": [],
            "sample_matches_note": None,
            "status": "available",
        }
        out.append(
            {
                "id": f"v03_{comp_id}",
                "label": label_it,
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "direction": _direction_label(val, predicted),
                "data_status": "ok",
                "notes": None,
                "variables": [var_row],
            },
        )
    return out


def _components_v04(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    comp = raw.get("offensive_production_component")
    dbg = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
    baseline_other = dbg.get("baseline_other_inputs")
    if not isinstance(comp, dict):
        return []
    inputs = comp.get("inputs")
    offensive_val = _safe_float(comp.get("value"))
    if offensive_val is None:
        return []

    out: list[dict[str, Any]] = []

    # 1) Sottovariabili componente offensiva
    subvars: list[dict[str, Any]] = []
    if isinstance(inputs, dict):
        for ik, blob in inputs.items():
            if not isinstance(blob, dict):
                continue
            w_in = _safe_float(blob.get("weight"))
            val = _safe_float(blob.get("value"))
            contrib_stored = blob.get("contribution")
            contrib = _safe_float(contrib_stored)
            if contrib is None and val is not None and w_in is not None:
                contrib = round(float(val) * float(w_in), 4)
            subvars.append(
                {
                    "key": str(ik),
                    "label": V04_OFFENSIVE_INPUT_LABELS.get(str(ik), str(ik)),
                    "value": _round2(val),
                    "unit": "misto" if ik == "offensive_trend" else ("tiri" if "shots" in str(ik) else "quota" if "accuracy" in str(ik) else "tiri in porta / goal"),
                    "weight_internal": w_in,
                    "contribution": contrib,
                    "formula": _formula_hint_v04_input(str(ik)),
                    "data_source": str(blob.get("source_table") or "fixture_team_stats / fixtures"),
                    "matches_count": blob.get("matches_count"),
                    "sum": blob.get("sum"),
                    "sample_rows_count": None,
                    "fallback_used": str(ik) in (comp.get("fallbacks_used") or []),
                    "cap_applied": bool(comp.get("cap_applied")),
                    "no_data_leakage_note": "Sì (solo partite precedenti alla fixture, salvo audit post-match)",
                    "sample_matches": [],
                    "sample_matches_note": None,
                    "status": str(blob.get("status") or "available"),
                },
            )

    ow = _safe_float(comp.get("weight_in_model")) or 0.30
    off_contrib = round(float(offensive_val) * float(ow), 4)
    out.append(
        {
            "id": "v04_offensive_production",
            "label": "Produzione offensiva (componente v0.4)",
            "value": _round2(offensive_val),
            "weight": ow,
            "contribution": off_contrib,
            "direction": _direction_label(offensive_val, predicted),
            "data_status": "fallback" if (comp.get("fallbacks_used") or []) else "ok",
            "notes": str(comp.get("explanation") or "")[:500] or None,
            "variables": subvars,
        },
    )

    # 2) Blocchi baseline letti da debug.baseline_other_inputs
    if isinstance(baseline_other, dict):
        for key, label, w in V04_BASELINE_KEYS_ORDER[1:]:
            val = _safe_float(baseline_other.get(key))
            if val is None:
                continue
            contrib = round(float(val) * float(w), 4)
            out.append(
                {
                    "id": f"v04_base_{key}",
                    "label": label,
                    "value": _round2(val),
                    "weight": w,
                    "contribution": contrib,
                    "direction": _direction_label(val, predicted),
                    "data_status": "ok",
                    "notes": None,
                    "variables": [
                        {
                            "key": key,
                            "label": label,
                            "value": _round2(val),
                            "unit": "tiri in porta",
                            "weight_internal": w,
                            "contribution": contrib,
                            "formula": "valore letto da baseline v0.1 (raw_json v0.1) / debug",
                            "data_source": "team_sot_predictions (baseline v0.1 breakdown)",
                            "matches_count": None,
                            "sum": None,
                            "sample_rows_count": None,
                            "fallback_used": False,
                            "cap_applied": False,
                            "no_data_leakage_note": "Sì",
                            "sample_matches": [],
                            "sample_matches_note": None,
                            "status": "available",
                        },
                    ],
                },
            )

    return out


def _v10_xg_component_block(
    raw: dict[str, Any],
    predicted: float,
    *,
    base_sot: float | None,
    xc: dict[str, Any],
) -> dict[str, Any]:
    fb = bool(xc.get("fallback_used")) or not bool(xc.get("xg_adjustment_applied"))
    adj_sot = _safe_float(xc.get("xg_adjustment_sot"))
    pct = _safe_float(xc.get("xg_adjustment_pct"))
    tfor = _safe_float(xc.get("team_avg_xg_for"))
    oconc = _safe_float(xc.get("opponent_avg_xg_conceded"))
    var_row = {
        "key": "expected_goals",
        "label": "xG / Expected goals",
        "value": _round2(tfor),
        "unit": "xG medi",
        "weight_internal": _safe_float(xc.get("xg_sensitivity")) or 0.10,
        "contribution": _round2(adj_sot),
        "formula": str(xc.get("formula") or "base_explicit_sot * xg_adjustment_pct"),
        "data_source": str(xc.get("source") or "fixtures/statistics::expected_goals"),
        "matches_count": xc.get("team_xg_sample_matches"),
        "sample_rows_count": xc.get("opponent_xg_conceded_sample_matches"),
        "fallback_used": fb,
        "cap_applied": bool(xc.get("cap_applied")),
        "no_data_leakage_note": "Sì (solo partite precedenti alla fixture)",
        "status": "fallback" if fb else "available",
    }
    return {
        "id": "v10_xg_quality",
        "label": "Qualità occasioni (xG)",
        "value": _round2(tfor),
        "weight": None,
        "contribution": _round2(adj_sot),
        "direction": "neutro",
        "data_status": "fallback" if fb else "ok",
        "notes": (
            f"xG medio concessi avversario: {_round2(oconc)}. "
            f"Correzione %: {round(float(pct or 0.0) * 100, 3)}%. "
            f"Fallback: {xc.get('fallback_reason')}"
            if fb
            else (
                f"xG medio concessi avversario: {_round2(oconc)}. "
                f"Base {_round2(base_sot)} + Δ xG {_round2(adj_sot)} = {_round2(predicted)}."
            )
        ),
        "variables": [var_row],
    }


def _v11_component_sub_vars(comp: dict[str, Any]) -> list[dict[str, Any]]:
    sub_vars: list[dict[str, Any]] = []
    for ik, blob in offensive_inputs_as_map(comp).items():
        if not isinstance(blob, dict):
            continue
        audit_note = str(blob.get("audit_note") or "").strip()
        sub_vars.append(
            {
                "key": str(ik),
                "label": str(blob.get("label") or ik),
                "value": _round2(_safe_float(blob.get("normalized_value") if blob.get("normalized_value") is not None else blob.get("value"))),
                "raw_value": _round2(_safe_float(blob.get("raw_value"))),
                "normalized_value": _round2(_safe_float(blob.get("normalized_value"))),
                "unit": "scala SOT",
                "weight_internal": _safe_float(blob.get("internal_weight")),
                "internal_weight": _safe_float(blob.get("internal_weight")),
                "contribution": _safe_float(blob.get("internal_contribution")),
                "internal_contribution": _safe_float(blob.get("internal_contribution")),
                "formula": audit_note or str(blob.get("formula") or ""),
                "data_source": str(blob.get("source_path") or blob.get("db_field") or ""),
                "api_source": str(blob.get("api_source") or ""),
                "matches_count": blob.get("sample_count"),
                "split_context": blob.get("split_context"),
                "fallback_used": False,
                "status": str(blob.get("status") or "available"),
                "no_data_leakage_note": "Sì (solo partite precedenti)",
            },
        )
    return sub_vars


def _v11_get_component(raw: dict[str, Any], key: str) -> dict[str, Any]:
    comp = raw.get(key) if isinstance(raw.get(key), dict) else {}
    if comp:
        return comp
    comps = raw.get("components") if isinstance(raw.get("components"), dict) else {}
    c = comps.get(key)
    return c if isinstance(c, dict) else {}


def _components_v11(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    """v1.1 stage 6: offensiva + difensiva + split + forma recente + xG + player layer."""
    off_w = float(V11_FORMULA_OFFENSIVE_WEIGHT)
    def_w = float(V11_FORMULA_DEFENSIVE_WEIGHT)
    split_w = float(V11_FORMULA_SPLIT_WEIGHT)
    recent_w = float(V11_FORMULA_RECENT_WEIGHT)
    xg_w = float(V11_FORMULA_XG_WEIGHT)
    player_w = float(V11_FORMULA_PLAYER_WEIGHT)
    if raw.get("prediction_valid") is False or str(raw.get("status") or "") == "incomplete":
        miss = raw.get("missing_required_fields") if isinstance(raw.get("missing_required_fields"), list) else []
        notes = [str(m.get("message") or m.get("feature_key")) for m in miss if isinstance(m, dict)]
        fq = str(raw.get("formula_quality_status") or "missing_required_data")
        note = f"Predizione incompleta ({fq}). " + ("; ".join(notes[:5]) if notes else "Rigenerare v1.1.")
        missing_card = {
            "value": None,
            "contribution": None,
            "direction": "neutro",
            "data_status": "missing",
            "notes": note,
            "variables": [],
        }
        return [
            {"id": "v11_offensive_production", "label": "Produzione offensiva composita", "weight": off_w, **missing_card},
            {"id": "v11_opponent_defensive_resistance", "label": "Resistenza difensiva avversaria", "weight": def_w, **missing_card},
            {"id": "v11_home_away_split", "label": "Split casa/trasferta", "weight": split_w, **missing_card},
            {"id": "v11_recent_form", "label": "Forma recente", "weight": recent_w, **missing_card},
            {"id": "v11_xg_chance_quality", "label": COMPONENT_LABEL_XG, "weight": xg_w, **missing_card},
            {"id": "v11_player_layer", "label": COMPONENT_LABEL_PLAYER, "weight": player_w, **missing_card},
        ]

    formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
    terms = formula.get("terms") if isinstance(formula.get("terms"), list) else []
    term_by_key = {str(t.get("key")): t for t in terms if isinstance(t, dict) and t.get("key")}

    off = _v11_get_component(raw, "offensive_production_component")
    defc = _v11_get_component(raw, "opponent_defensive_resistance_component")
    splitc = _v11_get_component(raw, "home_away_split_component")
    recentc = _v11_get_component(raw, "recent_form_component")
    xgc = _v11_get_component(raw, COMPONENT_KEY_XG)
    playerc = _v11_get_component(raw, COMPONENT_KEY_PLAYER)

    off_term = term_by_key.get("offensive_production_component", {})
    def_term = term_by_key.get("opponent_defensive_resistance_component", {})
    split_term = term_by_key.get("home_away_split_component", {})
    recent_term = term_by_key.get("recent_form_component", {})
    xg_term = term_by_key.get(COMPONENT_KEY_XG, {})
    player_term = term_by_key.get(COMPONENT_KEY_PLAYER, {})

    off_val = _round2(_safe_float(off.get("value") if off else off_term.get("value")))
    def_val = _round2(_safe_float(defc.get("value") if defc else def_term.get("value")))
    split_val = _round2(_safe_float(splitc.get("value") if splitc else split_term.get("value")))
    recent_val = _round2(_safe_float(recentc.get("value") if recentc else recent_term.get("value")))
    xg_val = _round2(_safe_float(xgc.get("value") if xgc else xg_term.get("value")))
    player_val = _round2(_safe_float(playerc.get("value") if playerc else player_term.get("value")))

    def _contrib(term: dict, val: float | None, w: float) -> float | None:
        c = _round2(_safe_float(term.get("contribution")))
        if c is None and val is not None:
            c = _round2(float(val) * w)
        return c

    off_contrib = _contrib(off_term, off_val, off_w)
    def_contrib = _contrib(def_term, def_val, def_w)
    split_contrib = _contrib(split_term, split_val, split_w)
    recent_contrib = _contrib(recent_term, recent_val, recent_w)
    xg_contrib = _contrib(xg_term, xg_val, xg_w)
    player_contrib = _contrib(player_term, player_val, player_w)

    split_note = f"Peso formula finale {int(split_w * 100)}%. Contesto split reale della partita."
    if splitc:
        sc = splitc.get("split_context")
        osc = splitc.get("opponent_split_context")
        if sc or osc:
            split_note += f" split_context={sc}; opponent_split_context={osc}."

    recent_note = (
        f"Peso formula finale {int(recent_w * 100)}%. Ultime 5 partite squadra e avversario "
        "(nessun fallback se campione insufficiente)."
    )
    xg_note = (
        f"Peso formula finale {int(xg_w * 100)}%. expected_goals da API-Football / fixture_team_stats; "
        "campione minimo 5 partite con xG per squadra e avversario; nessun fallback silenzioso."
    )
    pl_mode = str(playerc.get("mode") or "historical_recent_profile")
    if pl_mode == "lineup_adjusted":
        player_note = (
            f"Peso formula finale {int(player_w * 100)}%. Modalità: lineup-adjusted — "
            "titolari ufficiali da fixture_lineup_players + profili player_season_profiles; "
            "presenza/assenza top shooter integrate nel calcolo numerico."
        )
        la = playerc.get("lineup_adjustment") if isinstance(playerc.get("lineup_adjustment"), dict) else {}
        if la.get("status") == "applied":
            player_note += (
                f" Top shooter titolari: {la.get('top_shooters_starting')}/{la.get('top_shooters_total')}; "
                f"in panchina: {la.get('top_shooters_on_bench')}; "
                f"fuori distinta: {la.get('top_shooters_not_in_lineup')}."
            )
        starters = playerc.get("lineup_starters") if isinstance(playerc.get("lineup_starters"), list) else []
        if starters:
            sn = [str(p.get("name") or p.get("api_player_id")) for p in starters[:11] if isinstance(p, dict)]
            if sn:
                player_note += f" Titolari usati: {', '.join(sn)}."
    else:
        player_note = (
            f"Peso formula finale {int(player_w * 100)}%. "
            "Lineups non disponibili, Player layer in modalità storico/recent impact "
            "(top 5 da player_season_profiles, min 3 eleggibili, minuti ≥180)."
        )
    top_players = playerc.get("top_players") if isinstance(playerc.get("top_players"), list) else []
    if top_players and pl_mode != "lineup_adjusted":
        names = [str(p.get("name") or p.get("api_player_id")) for p in top_players[:5] if isinstance(p, dict)]
        if names:
            player_note += f" Top: {', '.join(names)}."

    return [
        {
            "id": "v11_offensive_production",
            "label": str(off.get("label") or "Produzione offensiva composita"),
            "value": off_val,
            "weight": off_w,
            "contribution": off_contrib,
            "direction": "neutro",
            "data_status": "ok",
            "notes": f"Peso formula finale {int(off_w * 100)}%. Componente interna: 9 input normalizzati.",
            "variables": _v11_component_sub_vars(off) if off else [],
        },
        {
            "id": "v11_opponent_defensive_resistance",
            "label": str(defc.get("label") or "Resistenza difensiva avversaria"),
            "value": def_val,
            "weight": def_w,
            "contribution": def_contrib,
            "direction": "neutro",
            "data_status": "ok",
            "notes": f"Peso formula finale {int(def_w * 100)}%. Concessi ricostruiti dalle stats degli avversari dell'avversario.",
            "variables": _v11_component_sub_vars(defc) if defc else [],
        },
        {
            "id": "v11_home_away_split",
            "label": str(splitc.get("label") or "Split casa/trasferta"),
            "value": split_val,
            "weight": split_w,
            "contribution": split_contrib,
            "direction": "neutro",
            "data_status": "ok",
            "notes": split_note,
            "variables": _v11_component_sub_vars(splitc) if splitc else [],
        },
        {
            "id": "v11_recent_form",
            "label": str(recentc.get("label") or "Forma recente"),
            "value": recent_val,
            "weight": recent_w,
            "contribution": recent_contrib,
            "direction": "neutro",
            "data_status": "ok",
            "notes": recent_note,
            "variables": _v11_component_sub_vars(recentc) if recentc else [],
        },
        {
            "id": "v11_xg_chance_quality",
            "label": str(xgc.get("label") or COMPONENT_LABEL_XG),
            "value": xg_val,
            "weight": xg_w,
            "contribution": xg_contrib,
            "direction": "neutro",
            "data_status": "ok",
            "notes": xg_note,
            "variables": _v11_component_sub_vars(xgc) if xgc else [],
        },
        {
            "id": "v11_player_layer",
            "label": str(playerc.get("label") or COMPONENT_LABEL_PLAYER),
            "value": player_val,
            "weight": player_w,
            "contribution": player_contrib,
            "direction": "neutro",
            "data_status": "ok",
            "notes": player_note,
            "variables": _v11_component_sub_vars(playerc) if playerc else [],
        },
    ]


def _build_formula_breakdown_v11(raw: dict[str, Any], stored: float) -> dict[str, Any]:
    formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
    if str(formula.get("type") or "") != "weighted_components":
        return {}
    terms_raw = formula.get("terms")
    if not isinstance(terms_raw, list) or not terms_raw:
        return {}
    terms: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    contrib_vals: list[float] = []
    for t in terms_raw:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key") or "")
        lab = str(t.get("label") or key)
        w = _safe_float(t.get("weight"))
        val = _safe_float(t.get("value"))
        contrib_stored = _safe_float(t.get("contribution"))
        contrib = round(float(contrib_stored or 0.0), 4) if contrib_stored is not None else None
        if w is None:
            continue
        if contrib is None and val is not None:
            contrib = round(float(val) * float(w), 4)
        if contrib is None:
            contrib = 0.0
        contrib_vals.append(contrib)
        calc_expr = _mul_expr(val, w) if val is not None else f"contributo salvato ({_round4(contrib)})"
        terms.append(
            {
                "id": f"v11_term_{key}",
                "label": lab,
                "symbol": key,
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "calc_expression": calc_expr,
                "status": t.get("status"),
            },
        )
        if val is not None:
            sym_parts.append(f"({lab} × {w})")
            num_parts.append(_mul_expr(val, w))
        else:
            sym_parts.append(f"(— × {w})")
            num_parts.append(f"{_round4(contrib)}")
    s = round(sum(contrib_vals), 4) if contrib_vals else None
    sum_c, delta, warn, wmsg = _checksum_block(s, stored)
    fq_warn = raw.get("formula_quality_warnings") if isinstance(raw.get("formula_quality_warnings"), list) else []
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "stored_predicted_sot": _round2(stored),
        "terms": terms,
        "formula_terms_count": len(terms_raw) if isinstance(terms_raw, list) else len(terms),
        "formula_quality_status": raw.get("formula_quality_status"),
        "formula_quality_warnings": fq_warn,
        "formula_symbolic": "expected_sot_v1_1 = " + " + ".join(sym_parts),
        "formula_numeric": "expected_sot_v1_1 = " + " + ".join(num_parts) + f"\n= {_round2(s)}",
        "components_table": [
            {
                "componente": t["label"],
                "valore_componente": t["value"],
                "peso": t["weight"],
                "calcolo_contributo": t["calc_expression"],
                "contributo_finale": t["contribution"],
                "status": t.get("status"),
            }
            for t in terms
        ],
        "sum_contributions": sum_c,
        "delta_vs_stored": delta,
        "checksum_warning": wmsg,
        "flags": {"cap_applied": False, "fallbacks_used": []},
    }


def _components_v10_feature_registry(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
    terms_raw = formula.get("terms") if isinstance(formula.get("terms"), list) else []
    xc = raw.get("xg_component") if isinstance(raw.get("xg_component"), dict) else {}
    base_sot = _safe_float(raw.get("base_explicit_sot_before_xg"))
    fq_status = str(raw.get("formula_quality_status") or "")
    fq_warn = raw.get("formula_quality_warnings")
    out: list[dict[str, Any]] = []

    off = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
    off_missing_note = (
        "Componente non disponibile nel raw_json salvato. Rigenerare v1.0 (generate-v10-sot)."
        if not off
        else ""
    )
    off_inputs = offensive_inputs_as_map(off) if off else {}
    if off and not off_inputs:
        off_missing_note = "Input interni assenti o vuoti nel raw_json. Rigenerare v1.0."
    sub_vars: list[dict[str, Any]] = []
    for ik, blob in off_inputs.items():
        if not isinstance(blob, dict):
            continue
        sub_vars.append(
            {
                "key": str(ik),
                "label": str(blob.get("label") or ik),
                "value": _round2(_safe_float(blob.get("normalized_value") if blob.get("normalized_value") is not None else blob.get("value"))),
                "raw_value": _round2(_safe_float(blob.get("raw_value"))),
                "normalized_value": _round2(_safe_float(blob.get("normalized_value"))),
                "unit": str(blob.get("unit") or "scala SOT"),
                "weight_internal": _safe_float(blob.get("internal_weight") if blob.get("internal_weight") is not None else blob.get("weight")),
                "internal_weight": _safe_float(blob.get("internal_weight") if blob.get("internal_weight") is not None else blob.get("weight")),
                "contribution": _safe_float(blob.get("internal_contribution") if blob.get("internal_contribution") is not None else blob.get("contribution")),
                "internal_contribution": _safe_float(blob.get("internal_contribution") if blob.get("internal_contribution") is not None else blob.get("contribution")),
                "formula": str(blob.get("formula") or ""),
                "data_source": str(blob.get("source_path") or blob.get("source_table") or ""),
                "matches_count": blob.get("sample_count") if blob.get("sample_count") is not None else blob.get("matches_count"),
                "fallback_used": bool(blob.get("fallback_used")),
                "status": str(blob.get("status") or "available"),
                "no_data_leakage_note": "Sì (solo partite precedenti)",
            },
        )
    out.append(
        {
            "id": "v10_offensive_production",
            "label": str(off.get("label") or "Produzione offensiva composita"),
            "value": _round2(_safe_float(off.get("value"))),
            "weight": _safe_float(off.get("weight_in_final_formula")) or _safe_float(off.get("weight_in_model")) or 0.30,
            "contribution": _round2(_safe_float(off.get("contribution_in_final_formula") or off.get("contribution"))),
            "direction": "neutro",
            "data_status": "fallback" if (off.get("fallbacks_used") or off_missing_note) else "ok",
            "notes": off_missing_note or str(off.get("explanation") or ""),
            "variables": sub_vars,
        },
    )

    exp_vars: list[dict[str, Any]] = []
    for t in terms_raw:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key") or "")
        if key in ("expected_goals", "offensive_production_component"):
            continue
        w = _safe_float(t.get("weight"))
        val = _safe_float(t.get("value"))
        contrib = _safe_float(t.get("contribution"))
        if contrib is None and val is not None and w is not None:
            contrib = round(float(val) * float(w), 4)
        exp_vars.append(
            {
                "key": key,
                "label": str(t.get("label") or key),
                "value": _round2(val),
                "unit": "tiri in porta" if key != "expected_goals" else "xG medi",
                "weight_internal": w,
                "contribution": contrib,
                "formula": str(t.get("formula") or ""),
                "data_source": str(t.get("source_path") or t.get("source") or "feature registry"),
                "fallback_used": bool(t.get("fallback_used")),
                "cap_applied": bool(t.get("cap_applied")),
                "no_data_leakage_note": "Sì (solo partite precedenti)",
                "status": str(t.get("status") or ("fallback" if t.get("fallback_used") else "available")),
            },
        )

    notes: list[str] = ["Architettura: feature registry DB + xG additivo."]
    if fq_status:
        notes.append(f"Qualità formula: {fq_status}.")
    if isinstance(fq_warn, list) and fq_warn:
        notes.append(" ".join(str(w) for w in fq_warn[:3]))

    out.append(
        {
            "id": "v10_explicit_weighted_sum",
            "label": "Formula esplicita modello v1.0 (registry)",
            "value": _round2(predicted),
            "weight": None,
            "contribution": _round2(predicted),
            "direction": "neutro",
            "data_status": "ok" if fq_status != "needs_review" else "fallback",
            "notes": " ".join(notes),
            "variables": exp_vars,
        },
    )
    if xc:
        out.append(_v10_xg_component_block(raw, predicted, base_sot=base_sot, xc=xc))
    return out


def _components_v10(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    arch = str(raw.get("architecture") or "")
    if arch.startswith("feature_registry") or arch == "explicit_feature_registry_sum":
        return _components_v10_feature_registry(raw, predicted)

    base_sot = _safe_float(raw.get("base_explicit_sot_before_xg"))
    ref_for_v04 = float(base_sot) if base_sot is not None else float(predicted)
    out = _components_v04(raw, ref_for_v04)

    formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
    terms_raw = formula.get("terms") if isinstance(formula.get("terms"), list) else []
    va = raw.get("v04_alignment") if isinstance(raw.get("v04_alignment"), dict) else {}
    v04ref = _safe_float(va.get("v04_expected_sot"))
    v10base = _safe_float(va.get("v10_expected_sot"))
    delta = _safe_float(va.get("delta"))
    status = str(va.get("status") or "")
    xc = raw.get("xg_component") if isinstance(raw.get("xg_component"), dict) else {}

    exp_vars: list[dict[str, Any]] = []
    for t in terms_raw:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key") or "")
        if key == "expected_goals":
            continue
        w = _safe_float(t.get("weight"))
        val = _safe_float(t.get("value"))
        contrib = _safe_float(t.get("contribution"))
        if contrib is None and val is not None and w is not None:
            contrib = round(float(val) * float(w), 4)
        exp_vars.append(
            {
                "key": key,
                "label": str(t.get("label") or key),
                "value": _round2(val),
                "unit": "tiri in porta",
                "weight_internal": w,
                "contribution": contrib,
                "formula": str(t.get("formula") or ""),
                "data_source": str(t.get("source") or "raw_json v0.4 / formula v1.0"),
                "matches_count": None,
                "sum": None,
                "sample_rows_count": None,
                "fallback_used": bool(t.get("fallback_used")),
                "cap_applied": bool(t.get("cap_applied")),
                "no_data_leakage_note": "Sì (valori letti da snapshot v0.4)",
                "sample_matches": [],
                "sample_matches_note": None,
                "status": "fallback" if t.get("fallback_used") else "available",
            },
        )

    notes_align: list[str] = []
    if v04ref is not None and v10base is not None and delta is not None:
        notes_align.append(
            f"Base esplicita vs `predicted_sot` v0.4: Δ = {_round2(delta)}. Stato: {status or '—'}.",
        )
    if arch in ("explicit_terms_from_v04_plus_xg", "explicit_terms_from_v04"):
        notes_align.append("Architettura: termini espliciti v0.4" + (" + correzione xG additiva." if "xg" in arch else "."))

    out.append(
        {
            "id": "v10_explicit_weighted_sum",
            "label": "Formula esplicita modello v1.0",
            "value": _round2(predicted),
            "weight": None,
            "contribution": _round2(predicted),
            "direction": "neutro",
            "data_status": "ok" if status != "needs_review" else "fallback",
            "notes": " ".join(notes_align) if notes_align else None,
            "variables": exp_vars,
        },
    )

    if xc:
        out.append(_v10_xg_component_block(raw, predicted, base_sot=base_sot, xc=xc))
    return out


def _formula_hint_v04_input(key: str) -> str:
    if key == "avg_sot_for":
        return "sum(shots_on_target) / matches_count"
    if key == "avg_total_shots_for":
        return "sum(total_shots) / matches_count"
    if key == "shot_accuracy_for":
        return "media SOT / media tiri (stagione)"
    if key == "avg_goals_for":
        return "sum(goal fatti) / matches_count"
    if key == "offensive_trend":
        return "blend(last5_sot, last10_sot) vs stagione"
    if "inside" in key:
        return "sum(shots_inside_box) / matches_count"
    if "outside" in key:
        return "sum(shots_outside_box) / matches_count"
    return "vedi raw_json.offensive_production_component.inputs"


def _components_v02(raw: dict[str, Any], predicted: float) -> list[dict[str, Any]]:
    base = _safe_float(raw.get("baseline_expected_sot"))
    adj = _safe_float(raw.get("total_adjustment")) or 0.0
    parts: list[dict[str, Any]] = []
    if base is not None:
        parts.append(
            {
                "id": "v02_baseline",
                "label": "Baseline v0.1 di partenza",
                "value": _round2(base),
                "weight": None,
                "contribution": _round2(base),
                "direction": "neutro",
                "data_status": "ok",
                "notes": "Valore di riferimento prima degli aggiustamenti contestuali.",
                "variables": [],
            },
        )
    bd = raw.get("adjustment_breakdown") if isinstance(raw.get("adjustment_breakdown"), dict) else {}
    labels = {
        "player": "Aggiustamento profilo giocatori",
        "h2h": "Aggiustamento H2H",
        "motivation": "Aggiustamento motivazione / contesto",
        "availability": "Aggiustamento disponibilità",
    }
    for k, lab in labels.items():
        sub = bd.get(k) if isinstance(bd.get(k), dict) else {}
        delta = _safe_float(sub.get("adjustment")) or _safe_float(sub.get("delta"))
        if delta is None or abs(delta) < 1e-9:
            continue
        parts.append(
            {
                "id": f"v02_adj_{k}",
                "label": lab,
                "value": _round2(delta),
                "weight": None,
                "contribution": _round2(delta),
                "direction": "aumenta" if delta > 0 else "riduce",
                "data_status": "ok",
                "notes": None,
                "variables": [],
            },
        )
    if base is not None:
        parts.append(
            {
                "id": "v02_total",
                "label": "Somma (baseline + aggiustamenti)",
                "value": _round2(predicted),
                "weight": 1.0,
                "contribution": _round2(predicted),
                "direction": "neutro",
                "data_status": "ok",
                "notes": f"Delta totale registrato: {_round2(adj)}.",
                "variables": [],
            },
        )
    return parts


def _build_side_components(model_version: str, raw: dict[str, Any] | None, predicted: float) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    if model_version == BASELINE_SOT_MODEL_VERSION:
        return _components_v01(raw, predicted)
    if model_version == BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT:
        return _components_v03(raw, predicted)
    if model_version == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
        return _components_v04(raw, predicted)
    if model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT:
        return _components_v11(raw, predicted)
    if model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT:
        return _components_v10(raw, predicted)
    if model_version in (BASELINE_SOT_MODEL_VERSION_V02, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED):
        return _components_v02(raw, predicted)
    return []


def _round4(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 4)


def _mul_expr(val: float | None, w: float | None) -> str:
    if val is None:
        return "—"
    if w is None:
        return f"{_round2(val)}"
    return f"({_round2(val)} × {_round4(w)})"


def _fixture_season_year(db: Session, fx: Fixture) -> int | None:
    yr = db.scalar(select(Season.year).where(Season.id == int(fx.season_id)))
    return int(yr) if yr is not None else None


def _v11_shot_coverage_remediation_hints(*, raw: dict[str, Any] | None, season_year: int | None) -> list[str]:
    if raw is None or raw.get("prediction_valid") is not False:
        return []
    miss = raw.get("missing_required_fields")
    hit_keys: set[str] = set()
    if isinstance(miss, list):
        for m in miss:
            if not isinstance(m, dict):
                continue
            fk = str(m.get("feature_key") or "")
            if fk in V11_BLOCKED_OFF_DIAG_KEYS:
                hit_keys.add(fk)
    if not hit_keys:
        return []
    ys = season_year if season_year is not None else "«season»"
    dbg = f"/api/admin/debug/serie-a/{ys}/team-shot-stats-summary"
    keys_it = sorted(hit_keys)
    return [
        f"baseline_v1_1_sot incompleta per: {', '.join(keys_it)}.",
        "API: endpoints fixtures/statistics con voci «Blocked Shots» e «Shots off Goal».",
        "DB: `fixture_team_stats.blocked_shots`, `fixture_team_stats.shots_off_goal` "
        "(in lettura v1.1 è supportato anche `raw_json.statistics` se persistito).",
        f"Diagnostica copertura (GET): `{dbg}`; rieseguire l'ingestion statistiche squadra da Admin.",
    ]


def _checksum_block(sum_contrib: float | None, stored: float | None) -> tuple[float | None, float | None, bool, str | None]:
    if sum_contrib is None or stored is None:
        return None, None, False, None
    delta = round(float(sum_contrib) - float(stored), 4)
    warn = abs(delta) > CHECKSUM_TOLERANCE
    return round(float(sum_contrib), 4), delta, warn, CHECKSUM_WARNING_IT if warn else None


def _build_formula_breakdown_v01(raw: dict[str, Any], stored: float) -> dict[str, Any]:
    weights = raw.get("weights")
    resolved = raw.get("resolved_inputs")
    inputs = raw.get("inputs")
    if not isinstance(weights, dict) or not isinstance(resolved, dict):
        return {}
    terms: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    contrib_vals: list[float] = []
    for key, w_def in WEIGHTS_BASELINE_V0_1.items():
        w = _safe_float(weights.get(key, w_def))
        val = _safe_float(resolved.get(key))
        if w is None or val is None:
            continue
        lab = V01_LABELS.get(key, key)
        contrib = round(float(val) * float(w), 4)
        contrib_vals.append(contrib)
        terms.append(
            {
                "id": f"v01_{key}",
                "label": lab,
                "symbol": key,
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "calc_expression": _mul_expr(val, w),
            },
        )
        sym_parts.append(f"({lab} × {w})")
        num_parts.append(_mul_expr(val, w))
    s = round(sum(contrib_vals), 4) if contrib_vals else None
    sum_c, delta, warn, wmsg = _checksum_block(s, stored)
    fb_list: list[str] = []
    if isinstance(inputs, dict):
        for fk in WEIGHTS_BASELINE_V0_1:
            if inputs.get(fk) is None:
                fb_list.append(str(fk))
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION,
        "stored_predicted_sot": _round2(stored),
        "terms": terms,
        "formula_symbolic": "expected_sot = " + " + ".join(sym_parts),
        "formula_numeric": "expected_sot = " + " + ".join(num_parts) + f"\n= {' + '.join(str(round(x, 4)) for x in contrib_vals)}\n= {_round2(s)}",
        "components_table": [
            {
                "componente": t["label"],
                "valore_componente": t["value"],
                "peso": t["weight"],
                "calcolo_contributo": t["calc_expression"],
                "contributo_finale": t["contribution"],
            }
            for t in terms
        ],
        "sum_contributions": sum_c,
        "delta_vs_stored": delta,
        "checksum_warning": wmsg,
        "flags": {
            "cap_applied": False,
            "fallbacks_used": fb_list,
        },
    }


def _build_formula_breakdown_v03(raw: dict[str, Any], stored: float) -> dict[str, Any]:
    comps = raw.get("components")
    wmap = raw.get("weights")
    if not isinstance(comps, dict) or not isinstance(wmap, dict):
        return {}
    terms: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    contrib_vals: list[float] = []
    for comp_id, label_it, comp_key, w_def in V03_COMPONENT_META:
        w = _safe_float(wmap.get(comp_key))
        if w is None:
            w = w_def
        cobj = comps.get(comp_key) if isinstance(comps, dict) else None
        val = _safe_float((cobj or {}).get("value")) if isinstance(cobj, dict) else None
        if val is None:
            continue
        contrib = round(float(val) * float(w), 4)
        contrib_vals.append(contrib)
        terms.append(
            {
                "id": f"v03_{comp_id}",
                "label": label_it,
                "symbol": comp_key,
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "calc_expression": _mul_expr(val, w),
            },
        )
        sym_parts.append(f"({label_it} × {w})")
        num_parts.append(_mul_expr(val, w))
    s = round(sum(contrib_vals), 4) if contrib_vals else None
    sum_c, delta, warn, wmsg = _checksum_block(s, stored)
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
        "stored_predicted_sot": _round2(stored),
        "terms": terms,
        "formula_symbolic": "expected_sot = " + " + ".join(sym_parts),
        "formula_numeric": "expected_sot = " + " + ".join(num_parts) + f"\n= {' + '.join(str(round(x, 4)) for x in contrib_vals)}\n= {_round2(s)}",
        "components_table": [
            {
                "componente": t["label"],
                "valore_componente": t["value"],
                "peso": t["weight"],
                "calcolo_contributo": t["calc_expression"],
                "contributo_finale": t["contribution"],
            }
            for t in terms
        ],
        "sum_contributions": sum_c,
        "delta_vs_stored": delta,
        "checksum_warning": wmsg,
        "flags": {"cap_applied": False, "fallbacks_used": []},
    }


def _build_formula_breakdown_v04(raw: dict[str, Any], stored: float) -> dict[str, Any]:
    comp = raw.get("offensive_production_component")
    dbg = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
    baseline_other = dbg.get("baseline_other_inputs")
    if not isinstance(comp, dict) or not isinstance(baseline_other, dict):
        return {}
    offensive_val = _safe_float(comp.get("value"))
    if offensive_val is None:
        return {}
    ow = _safe_float(comp.get("weight_in_model")) or 0.30
    terms: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    contrib_vals: list[float] = []

    lab0 = "Produzione offensiva (componente)"
    c0 = round(float(offensive_val) * float(ow), 4)
    contrib_vals.append(c0)
    terms.append(
        {
            "id": "v04_offensive",
            "label": lab0,
            "symbol": "offensive_production_component",
            "value": _round2(offensive_val),
            "weight": ow,
            "contribution": c0,
            "calc_expression": _mul_expr(offensive_val, ow),
        },
    )
    sym_parts.append(f"({lab0} × {ow})")
    num_parts.append(_mul_expr(offensive_val, ow))

    for key, label, w in V04_BASELINE_KEYS_ORDER[1:]:
        val = _safe_float(baseline_other.get(key))
        if val is None:
            continue
        contrib = round(float(val) * float(w), 4)
        contrib_vals.append(contrib)
        terms.append(
            {
                "id": f"v04_{key}",
                "label": label,
                "symbol": key,
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "calc_expression": _mul_expr(val, w),
            },
        )
        sym_parts.append(f"({label} × {w})")
        num_parts.append(_mul_expr(val, w))

    s = round(sum(contrib_vals), 4) if contrib_vals else None
    sum_c, delta, warn, wmsg = _checksum_block(s, stored)
    fb = comp.get("fallbacks_used") if isinstance(comp.get("fallbacks_used"), list) else []
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        "stored_predicted_sot": _round2(stored),
        "terms": terms,
        "formula_symbolic": "expected_sot = " + " + ".join(sym_parts),
        "formula_numeric": "expected_sot = " + " + ".join(num_parts) + f"\n= {' + '.join(str(round(x, 4)) for x in contrib_vals)}\n= {_round2(s)}",
        "components_table": [
            {
                "componente": t["label"],
                "valore_componente": t["value"],
                "peso": t["weight"],
                "calcolo_contributo": t["calc_expression"],
                "contributo_finale": t["contribution"],
            }
            for t in terms
        ],
        "sum_contributions": sum_c,
        "delta_vs_stored": delta,
        "checksum_warning": wmsg,
        "flags": {
            "cap_applied": bool(comp.get("cap_applied")),
            "fallbacks_used": [str(x) for x in fb],
        },
    }


def _build_formula_breakdown_v10(raw: dict[str, Any], stored: float) -> dict[str, Any]:
    formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
    ftype = str(formula.get("type") or "")
    if ftype not in ("weighted_sum", "explicit_weighted_sum_plus_adjustments", "explicit_feature_registry_sum"):
        return {}
    terms_raw = formula.get("terms")
    if not isinstance(terms_raw, list) or not terms_raw:
        return {}
    terms: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    contrib_vals: list[float] = []
    for t in terms_raw:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key") or "")
        lab = str(t.get("label") or key)
        w = _safe_float(t.get("weight"))
        val = _safe_float(t.get("value"))
        contrib_stored = _safe_float(t.get("contribution"))
        contrib = round(float(contrib_stored or 0.0), 4) if contrib_stored is not None else None
        if key == "expected_goals":
            if contrib is None:
                contrib = 0.0
            terms.append(
                {
                    "id": "v10_term_expected_goals",
                    "label": lab,
                    "symbol": key,
                    "value": _round2(val),
                    "weight": w,
                    "contribution": contrib,
                    "calc_expression": f"xG_adjustment({_round2(contrib)})",
                    "source_path": str(t.get("source_path") or t.get("source") or ""),
                    "fallback_used": bool(t.get("fallback_used")),
                    "fallback_reason": t.get("fallback_reason"),
                    "status": t.get("status"),
                },
            )
            sym_parts.append(f"xG_adjustment({_round2(contrib)})")
            num_parts.append(f"{_round4(contrib)}")
            contrib_vals.append(contrib)
            continue
        if w is None:
            continue
        if contrib is None and val is not None:
            contrib = round(float(val) * float(w), 4)
        if contrib is None:
            contrib = 0.0
        contrib_vals.append(contrib)
        calc_expr = _mul_expr(val, w) if val is not None else f"contributo salvato ({_round4(contrib)})"
        terms.append(
            {
                "id": f"v10_term_{key}",
                "label": lab,
                "symbol": key,
                "value": _round2(val),
                "weight": w,
                "contribution": contrib,
                "calc_expression": calc_expr,
                "source_path": str(t.get("source_path") or t.get("source") or ""),
                "fallback_used": bool(t.get("fallback_used")),
                "fallback_reason": t.get("fallback_reason"),
                "status": t.get("status"),
            },
        )
        if val is not None:
            sym_parts.append(f"({lab} × {w})")
            num_parts.append(_mul_expr(val, w))
        else:
            sym_parts.append(f"(— × {w})")
            num_parts.append(f"{_round4(contrib)}")
    s = round(sum(contrib_vals), 4) if contrib_vals else None
    sum_c, delta, warn, wmsg = _checksum_block(s, stored)
    va = raw.get("v04_alignment") if isinstance(raw.get("v04_alignment"), dict) else {}
    xc = raw.get("xg_component") if isinstance(raw.get("xg_component"), dict) else {}
    fb_list: list[str] = []
    if va.get("status") == "needs_review":
        fb_list.append("v04_alignment_needs_review")
    if xc.get("fallback_used"):
        fb_list.append("xg_fallback")
    fq_warn = raw.get("formula_quality_warnings") if isinstance(raw.get("formula_quality_warnings"), list) else []
    for w in fq_warn:
        if isinstance(w, str) and w and w not in fb_list:
            fb_list.append(w)
    if raw.get("formula_quality_status") == "needs_review":
        fb_list.append("formula_quality_needs_review")
    sym_extra = str(formula.get("symbolic") or "").strip()
    num_extra = str(formula.get("numeric") or "").strip()
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V10_SOT,
        "stored_predicted_sot": _round2(stored),
        "terms": terms,
        "formula_terms_count": len(terms_raw) if isinstance(terms_raw, list) else len(terms),
        "formula_quality_status": raw.get("formula_quality_status"),
        "formula_quality_warnings": fq_warn,
        "formula_symbolic": sym_extra or ("expected_sot_v1 = " + " + ".join(sym_parts)),
        "formula_numeric": num_extra or ("expected_sot_v1 = " + " + ".join(num_parts) + f"\n= {_round2(s)}"),
        "components_table": [
            {
                "componente": t["label"],
                "valore_componente": t["value"],
                "peso": t["weight"],
                "calcolo_contributo": t["calc_expression"],
                "contributo_finale": t["contribution"],
                "source_path": t.get("source_path"),
                "fallback_used": t.get("fallback_used"),
                "fallback_reason": t.get("fallback_reason"),
                "status": t.get("status"),
            }
            for t in terms
        ],
        "sum_contributions": sum_c,
        "delta_vs_stored": delta,
        "checksum_warning": wmsg,
        "flags": {
            "cap_applied": bool(xc.get("cap_applied")),
            "fallbacks_used": fb_list,
            "v04_alignment": {
                "status": va.get("status"),
                "delta": _safe_float(va.get("delta")),
            },
            "base_sum": _safe_float(formula.get("base_sum")),
            "adjustment_sum": _safe_float(formula.get("adjustment_sum")),
        },
    }


def _build_formula_breakdown_v02(raw: dict[str, Any], stored: float) -> dict[str, Any]:
    base = _safe_float(raw.get("baseline_expected_sot"))
    bd = raw.get("adjustment_breakdown") if isinstance(raw.get("adjustment_breakdown"), dict) else {}
    labels = {
        "player": "Aggiustamento profilo giocatori",
        "h2h": "Aggiustamento H2H",
        "motivation": "Aggiustamento motivazione / contesto",
        "availability": "Aggiustamento disponibilità",
    }
    terms: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    contrib_vals: list[float] = []
    if base is not None:
        terms.append(
            {
                "id": "v02_baseline",
                "label": "Baseline v0.1",
                "symbol": "baseline",
                "value": _round2(base),
                "weight": None,
                "contribution": _round2(base),
                "calc_expression": f"{_round2(base)}",
            },
        )
        sym_parts.append("baseline_v0_1")
        num_parts.append(f"{_round2(base)}")
        contrib_vals.append(float(base))
    for k, lab in labels.items():
        sub = bd.get(k) if isinstance(bd.get(k), dict) else {}
        delta = _safe_float(sub.get("adjustment")) or _safe_float(sub.get("delta"))
        if delta is None or abs(delta) < 1e-9:
            continue
        terms.append(
            {
                "id": f"v02_{k}",
                "label": lab,
                "symbol": k,
                "value": _round2(delta),
                "weight": None,
                "contribution": _round2(delta),
                "calc_expression": f"{float(delta):+.4f}",
            },
        )
        sym_parts.append(lab)
        num_parts.append(f"({delta:+.4f})")
        contrib_vals.append(float(delta))
    s = round(sum(contrib_vals), 4) if contrib_vals else None
    sum_c, delta, warn, wmsg = _checksum_block(s, stored)
    return {
        "model_version": str(raw.get("model_version") or BASELINE_SOT_MODEL_VERSION_V02),
        "stored_predicted_sot": _round2(stored),
        "terms": terms,
        "formula_symbolic": "expected_sot = " + " + ".join(sym_parts),
        "formula_numeric": "expected_sot = " + " + ".join(num_parts) + f"\n= {_round2(s)}",
        "components_table": [
            {
                "componente": t["label"],
                "valore_componente": t["value"],
                "peso": t["weight"],
                "calcolo_contributo": t["calc_expression"],
                "contributo_finale": t["contribution"],
            }
            for t in terms
        ],
        "sum_contributions": sum_c,
        "delta_vs_stored": delta,
        "checksum_warning": wmsg,
        "flags": {"cap_applied": False, "fallbacks_used": []},
    }


def _build_prediction_formula_breakdown_side(
    model_version: str,
    raw: dict[str, Any] | None,
    stored_predicted: float | None,
) -> dict[str, Any] | None:
    if stored_predicted is None or not isinstance(raw, dict):
        return None
    st = float(stored_predicted)
    if model_version == BASELINE_SOT_MODEL_VERSION:
        out = _build_formula_breakdown_v01(raw, st)
    elif model_version == BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT:
        out = _build_formula_breakdown_v03(raw, st)
    elif model_version == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
        out = _build_formula_breakdown_v04(raw, st)
    elif model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT:
        out = _build_formula_breakdown_v10(raw, st)
    elif model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT:
        out = _build_formula_breakdown_v11(raw, st)
    elif model_version in (BASELINE_SOT_MODEL_VERSION_V02, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED):
        out = _build_formula_breakdown_v02(raw, st)
    else:
        return None
    if not out or not out.get("terms"):
        return None
    return out


def _internal_formula_v04_offensive(comp: dict[str, Any], raw_root: dict[str, Any]) -> dict[str, Any]:
    inputs = comp.get("inputs")
    dbg_top = raw_root.get("debug") if isinstance(raw_root.get("debug"), dict) else {}
    rows: list[dict[str, Any]] = []
    sym_parts: list[str] = []
    num_parts: list[str] = []
    num_vals: list[float] = []
    sum_w = 0.0
    sum_num = 0.0
    def _append_input_row(ik: str, blob: dict[str, Any]) -> None:
        nonlocal sum_w, sum_num
        w_in = _safe_float(blob.get("internal_weight") if blob.get("internal_weight") is not None else blob.get("weight")) or 0.0
        val = _safe_float(
            blob.get("normalized_value")
            if blob.get("normalized_value") is not None
            else blob.get("value"),
        )
        cb = _safe_float(
            blob.get("internal_contribution") if blob.get("internal_contribution") is not None else blob.get("contribution"),
        )
        if cb is None and val is not None:
            cb = round(float(val) * float(w_in), 4) if w_in else None
        lab = str(blob.get("label") or V04_OFFENSIVE_INPUT_LABELS.get(str(ik), str(ik)))
        rows.append(
            {
                "key": str(ik),
                "label": lab,
                "value": _round2(val),
                "raw_value": _round2(_safe_float(blob.get("raw_value"))),
                "normalized_value": _round2(_safe_float(blob.get("normalized_value"))),
                "weight": w_in if w_in else None,
                "contribution": cb,
                "calc_expression": _mul_expr(val, w_in) if w_in else str(_round2(val)),
            },
        )
        if w_in and w_in > 0 and val is not None:
            sym_parts.append(f"({lab} × {w_in})")
            num_parts.append(_mul_expr(val, w_in))
            cbb = float(cb) if cb is not None else float(val) * float(w_in)
            num_vals.append(round(cbb, 4))
            sum_w += float(w_in)
            sum_num += cbb

    if isinstance(inputs, dict):
        for ik, blob in inputs.items():
            if isinstance(blob, dict):
                _append_input_row(str(ik), blob)
    elif isinstance(inputs, list):
        for blob in inputs:
            if isinstance(blob, dict) and blob.get("key"):
                _append_input_row(str(blob.get("key")), blob)
    capped = _safe_float(comp.get("value"))
    raw_uncapped = _safe_float(dbg_top.get("raw_component_value")) if isinstance(dbg_top, dict) else None
    cap_bounds = dbg_top.get("cap_bounds") if isinstance(dbg_top, dict) else None
    cap_applied = bool(comp.get("cap_applied"))
    fb = comp.get("fallbacks_used") if isinstance(comp.get("fallbacks_used"), list) else []
    notes: list[str] = [
        "Il componente offensivo in produzione combina segnali in scala SOT con media pesata (somma(val×peso)/somma(pesi)) "
        "prima dell'eventuale cap ±0.75 sulla media SOT di riferimento.",
    ]
    if sum_w > 0:
        blend = round(sum_num / sum_w, 4)
        notes.append(f"Media pesata dai contributi salvati (display): {blend} (denominatore pesi: {round(sum_w, 4)}).")
    if raw_uncapped is not None and capped is not None and (cap_applied or abs(float(raw_uncapped) - float(capped)) > 0.01):
        notes.append(f"Valore grezzo (pre-cap, da raw_json): {raw_uncapped}; valore salvato componente: {capped}.")
    if cap_bounds:
        notes.append(f"Limiti cap (da raw_json): {cap_bounds}.")
    sum_line = " + ".join(num_parts) if num_parts else ""
    sum_nums = " + ".join(str(x) for x in num_vals) if num_vals else ""
    return {
        "title": "offensive_production_component",
        "formula_symbolic": "blend ≈ " + " + ".join(sym_parts) + " (normalizzato; vedi nota)",
        "formula_numeric": ("contributi numeratore: " + sum_line + (f"\n= {sum_nums}" if sum_nums else "")),
        "rows": rows,
        "notes": notes,
        "flags": {"cap_applied": cap_applied, "fallbacks_used": [str(x) for x in fb]},
    }


def _internal_formula_v03_component(raw: dict[str, Any], comp_key: str, comp_label: str) -> dict[str, Any] | None:
    comps = raw.get("components")
    inputs = raw.get("inputs")
    resolved = raw.get("resolved_inputs")
    if not isinstance(comps, dict):
        return None
    cobj = comps.get(comp_key)
    if not isinstance(cobj, dict):
        return None
    formula = str(cobj.get("formula") or comp_key)
    rows: list[dict[str, Any]] = []
    keys = V03_INCLUDES_BY_COMP.get(comp_key, [])
    for k in keys:
        iv = inputs.get(k) if isinstance(inputs, dict) else None
        rv = resolved.get(k) if isinstance(resolved, dict) else None
        rows.append(
            {
                "key": k,
                "label": k,
                "value": _round2(_safe_float(rv if rv is not None else iv)),
                "raw_input": iv,
                "resolved": _round2(_safe_float(rv)) if rv is not None else None,
            },
        )
    return {
        "title": comp_key,
        "formula_text": formula,
        "component_value": _round2(_safe_float(cobj.get("value"))),
        "rows": rows,
        "notes": ["Valore componente e formula sono quelli persistiti in raw_json (nessun ricalcolo)."],
        "flags": {"cap_applied": False, "fallbacks_used": []},
    }


def _enrich_components_with_internal_formula(model_version: str, raw: dict[str, Any] | None, components: list[dict[str, Any]]) -> None:
    if not isinstance(raw, dict) or not components:
        return
    for comp in components:
        cid = str(comp.get("id") or "")
        if model_version in (BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, BASELINE_SOT_MODEL_VERSION_V10_SOT) and cid.startswith("v04_base_"):
            vars_ = comp.get("variables") or []
            if vars_ and isinstance(vars_[0], dict):
                v0 = vars_[0]
                comp["internal_formula"] = {
                    "title": str(comp.get("label") or cid),
                    "formula_text": "Contributo alla previsione finale = valore × peso (letto da baseline v0.1 / debug).",
                    "rows": [v0],
                    "notes": [],
                    "flags": {"cap_applied": False, "fallbacks_used": []},
                }
        elif model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT and cid == "v11_offensive_production":
            ocomp = _v11_get_component(raw, "offensive_production_component")
            if ocomp:
                comp["internal_formula"] = _internal_formula_v04_offensive(ocomp, raw)
        elif model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT and cid == "v11_opponent_defensive_resistance":
            dcomp = _v11_get_component(raw, "opponent_defensive_resistance_component")
            if dcomp:
                comp["internal_formula"] = _internal_formula_v04_offensive(dcomp, raw)
        elif model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT and cid == "v11_home_away_split":
            scomp = _v11_get_component(raw, "home_away_split_component")
            if scomp:
                comp["internal_formula"] = _internal_formula_v04_offensive(scomp, raw)
        elif model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT and cid == "v11_recent_form":
            rcomp = _v11_get_component(raw, "recent_form_component")
            if rcomp:
                comp["internal_formula"] = _internal_formula_v04_offensive(rcomp, raw)
        elif model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT and cid == "v11_xg_chance_quality":
            xcomp = _v11_get_component(raw, COMPONENT_KEY_XG)
            if xcomp:
                comp["internal_formula"] = _internal_formula_v04_offensive(xcomp, raw)
        elif model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT and cid == "v10_offensive_production":
            ocomp = raw.get("offensive_production_component")
            if isinstance(ocomp, dict):
                comp["internal_formula"] = _internal_formula_v04_offensive(ocomp, raw)
        elif model_version in (BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, BASELINE_SOT_MODEL_VERSION_V10_SOT) and cid == "v04_offensive_production":
            ocomp = raw.get("offensive_production_component")
            if isinstance(ocomp, dict):
                comp["internal_formula"] = _internal_formula_v04_offensive(ocomp, raw)
        elif model_version == BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT and cid.startswith("v03_"):
            ck = cid.replace("v03_", "")
            inf = _internal_formula_v03_component(raw, ck, str(comp.get("label") or ck))
            if inf:
                comp["internal_formula"] = inf
        elif model_version == BASELINE_SOT_MODEL_VERSION and cid.startswith("v01_"):
            vars_ = comp.get("variables") or []
            if vars_ and isinstance(vars_[0], dict):
                v0 = vars_[0]
                comp["internal_formula"] = {
                    "title": str(comp.get("label") or cid),
                    "formula_text": str(v0.get("formula") or ""),
                    "rows": [v0],
                    "notes": [],
                    "flags": {
                        "cap_applied": False,
                        "fallbacks_used": [str(v0.get("key") or "")] if v0.get("fallback_used") else [],
                    },
                }
        elif model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT and cid == "v10_explicit_weighted_sum":
            formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
            va = raw.get("v04_alignment") if isinstance(raw.get("v04_alignment"), dict) else {}
            comp["internal_formula"] = {
                "title": str(comp.get("label") or "Formula esplicita v1.0"),
                "formula_text": str(formula.get("symbolic") or formula.get("type") or "weighted_sum"),
                "rows": [
                    {
                        "key": "v04_alignment",
                        "label": "Allineamento base vs v0.4 (predicted_sot)",
                        "value": _round2(_safe_float(va.get("delta"))),
                    },
                    {
                        "key": "alignment_status",
                        "label": "Stato",
                        "value": str(va.get("status") or ""),
                    },
                ],
                "notes": [str(formula.get("numeric") or "").strip()] if formula.get("numeric") else [],
                "flags": {
                    "cap_applied": False,
                    "fallbacks_used": (["needs_review"] if va.get("status") == "needs_review" else []),
                },
            }
        elif model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT and cid == "v10_xg_quality":
            xc = raw.get("xg_component") if isinstance(raw.get("xg_component"), dict) else {}
            rows = [
                {"key": "team_avg_xg_for", "label": "xG medio squadra", "value": _round2(_safe_float(xc.get("team_avg_xg_for")))},
                {
                    "key": "opponent_avg_xg_conceded",
                    "label": "xG medio concessi avversario",
                    "value": _round2(_safe_float(xc.get("opponent_avg_xg_conceded"))),
                },
                {"key": "league_avg_xg_for", "label": "xG medio lega (fatti)", "value": _round2(_safe_float(xc.get("league_avg_xg_for")))},
                {
                    "key": "league_avg_xg_conceded",
                    "label": "xG medio lega (concessi)",
                    "value": _round2(_safe_float(xc.get("league_avg_xg_conceded"))),
                },
                {"key": "attack_xg_delta", "label": "Delta offensivo xG", "value": _round2(_safe_float(xc.get("attack_xg_delta")))},
                {"key": "opponent_xg_delta", "label": "Delta avversario xG", "value": _round2(_safe_float(xc.get("opponent_xg_delta")))},
                {"key": "xg_adjustment_pct", "label": "xg_adjustment_pct", "value": _round2(_safe_float(xc.get("xg_adjustment_pct")))},
                {"key": "xg_adjustment_sot", "label": "Contributo SOT (Δ)", "value": _round2(_safe_float(xc.get("xg_adjustment_sot")))},
                {
                    "key": "team_xg_sample_matches",
                    "label": "Sample partite squadra",
                    "value": xc.get("team_xg_sample_matches"),
                },
                {
                    "key": "opponent_xg_conceded_sample_matches",
                    "label": "Sample concessi avversario",
                    "value": xc.get("opponent_xg_conceded_sample_matches"),
                },
            ]
            comp["internal_formula"] = {
                "title": str(comp.get("label") or "xG"),
                "formula_text": "expected_sot_v1 = base_explicit_sot + (base_explicit_sot * xg_adjustment_pct)",
                "rows": rows,
                "notes": ([str(xc.get("fallback_reason") or "fallback")] if xc.get("fallback_used") else []),
                "flags": {
                    "cap_applied": bool(xc.get("cap_applied")),
                    "fallbacks_used": ["xg"] if xc.get("fallback_used") else [],
                },
            }
        elif model_version in (BASELINE_SOT_MODEL_VERSION_V02, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED):
            comp["internal_formula"] = {
                "title": str(comp.get("label") or cid),
                "formula_text": str(comp.get("notes") or ""),
                "rows": [],
                "notes": ["Somma additiva baseline + aggiustamenti (v0.2)."],
                "flags": {"cap_applied": False, "fallbacks_used": []},
            }


def _flatten_audit_variables(audit: MatchVariablesAuditResponse) -> dict[tuple[int, str], Any]:
    m: dict[tuple[int, str], Any] = {}
    for sec in audit.sections:
        for v in sec.variables:
            tid = int(v.team_id) if v.team_id is not None else -1
            m[(tid, v.key)] = v.model_dump(mode="json")
    return m


def _attach_samples_to_v04_variables(
    components: list[dict[str, Any]],
    team_id: int,
    audit_map: dict[tuple[int, str], Any],
) -> None:
    for comp in components:
        for var in comp.get("variables") or []:
            if not isinstance(var, dict):
                continue
            ik = str(var.get("key") or "")
            audit_key = V04_INPUT_TO_AUDIT_KEY.get(ik)
            if not audit_key:
                continue
            src = audit_map.get((team_id, audit_key))
            if not isinstance(src, dict):
                continue
            var["sample_matches"] = src.get("sample_rows") or []
            meta = (src.get("calculation") or {}).get("meta") if isinstance(src.get("calculation"), dict) else {}
            if isinstance(meta, dict):
                var["matches_count"] = var.get("matches_count") or meta.get("matches_count") or meta.get("total_matches_count")
                var["sum"] = var.get("sum") if var.get("sum") is not None else meta.get("sum")
            var["sample_rows_count"] = meta.get("sample_rows_count") if isinstance(meta, dict) else len(var["sample_matches"])
            total_m = meta.get("total_matches_count") if isinstance(meta, dict) else None
            if total_m and isinstance(var["sample_matches"], list) and len(var["sample_matches"]) < int(total_m):
                var["sample_matches_note"] = (
                    f"Il calcolo usa tutte le partite valide: {int(total_m)}. "
                    f"Qui ne mostriamo {len(var['sample_matches'])}."
                )


def _audit_lookup_key_v01(ik: str, *, team_id: int, fixture: Fixture) -> tuple[int, str] | None:
    hid, aid = int(fixture.home_team_id), int(fixture.away_team_id)
    if ik == "season_avg_sot_for":
        return team_id, "season_avg_sot_for"
    if ik == "opponent_season_avg_sot_conceded":
        return team_id, "opponent_season_avg_sot_conceded"
    if ik == "last5_avg_sot_for":
        return team_id, "last5_avg_sot_for"
    if ik == "opponent_last5_avg_sot_conceded":
        return team_id, "opponent_last5_avg_sot_conceded"
    if ik == "home_away_avg_sot_for":
        return (team_id, "home_avg_sot_for") if team_id == hid else (team_id, "away_avg_sot_for")
    if ik == "opponent_home_away_avg_sot_conceded":
        # Avversario in trasferta → split away concessi; in casa → split home concessi
        if team_id == hid:
            return aid, "away_avg_sot_conceded"
        return hid, "home_avg_sot_conceded"
    return None


def _attach_samples_v01(
    components: list[dict[str, Any]],
    team_id: int,
    audit_map: dict[tuple[int, str], Any],
    fixture: Fixture,
) -> None:
    for comp in components:
        for var in comp.get("variables") or []:
            if not isinstance(var, dict):
                continue
            ik = str(var.get("key") or "")
            lk = _audit_lookup_key_v01(ik, team_id=team_id, fixture=fixture)
            if lk is None:
                continue
            src = audit_map.get(lk)
            if not isinstance(src, dict):
                continue
            var["sample_matches"] = src.get("sample_rows") or []
            meta = (src.get("calculation") or {}).get("meta") if isinstance(src.get("calculation"), dict) else {}
            if isinstance(meta, dict):
                var["matches_count"] = var.get("matches_count") or meta.get("matches_count") or meta.get("total_matches_count")
                var["sum"] = var.get("sum") if var.get("sum") is not None else meta.get("sum")
            total_m = meta.get("total_matches_count") if isinstance(meta, dict) else None
            if total_m and isinstance(var["sample_matches"], list) and len(var["sample_matches"]) < int(total_m):
                var["sample_matches_note"] = (
                    f"Il calcolo usa tutte le partite valide: {int(total_m)}. "
                    f"Qui ne mostriamo {len(var['sample_matches'])}."
                )


def _attach_samples_v03(
    components: list[dict[str, Any]],
    team_id: int,
    audit_map: dict[tuple[int, str], Any],
    includes_by_comp: dict[str, list[str]],
) -> None:
    for comp in components:
        cid = str(comp.get("id") or "")
        pref = cid.replace("v03_", "")
        keys = includes_by_comp.get(pref, [])
        for var in comp.get("variables") or []:
            if not isinstance(var, dict):
                continue
            samples_merged: list[dict[str, Any]] = []
            for ak in keys:
                src = audit_map.get((team_id, ak))
                if isinstance(src, dict) and src.get("sample_rows"):
                    samples_merged.extend(src["sample_rows"])
            if samples_merged:
                var["sample_matches"] = samples_merged[:15]
                var["sample_matches_note"] = "Campione aggregato dalle variabili di input del componente."


def _human_summary(
    *,
    home_name: str,
    away_name: str,
    ph: float | None,
    pa: float | None,
    row_h: TeamSotPrediction | None,
    row_a: TeamSotPrediction | None,
    raw_h: dict[str, Any] | None,
    raw_a: dict[str, Any] | None,
) -> str:
    chunks: list[str] = []
    if ph is not None and pa is not None:
        chunks.append(
            f"Il modello stimato attribuisce circa {ph:.1f} tiri in porta a {home_name} e {pa:.1f} a {away_name} "
            f"(totale match ~{ph + pa:.1f}).",
        )
    for name, row, raw in (
        (home_name, row_h, raw_h),
        (away_name, row_a, raw_a),
    ):
        if row and row.explanation:
            chunks.append(f"{name}: {row.explanation}")
        if isinstance(raw, dict):
            comp = raw.get("offensive_production_component")
            if isinstance(comp, dict) and comp.get("explanation"):
                chunks.append(f"Dettaglio componente offensiva ({name}): {comp.get('explanation')}")
            fb = comp.get("fallbacks_used") if isinstance(comp, dict) else None
            if isinstance(fb, list) and fb:
                chunks.append(f"Fallback registrati per {name}: {', '.join(str(x) for x in fb)}.")
            if isinstance(comp, dict) and comp.get("cap_applied"):
                chunks.append(f"Per {name} risulta applicato un cap sulla componente offensiva.")
    return " ".join(chunks) if chunks else "Spiegazione non disponibile: mancano testi salvati sulla previsione."


def _build_component_tree_side(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in components:
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "component_key": c.get("id"),
                "component_label": c.get("label"),
                "value": c.get("value"),
                "weight": c.get("weight"),
                "contribution": c.get("contribution"),
                "data_status": c.get("data_status"),
                "notes": c.get("notes"),
                "variables": c.get("variables") if isinstance(c.get("variables"), list) else [],
            },
        )
    return out


def _build_final_formula_side(fb: dict[str, Any] | None) -> dict[str, Any] | None:
    if not fb or not isinstance(fb, dict):
        return None
    terms = fb.get("terms") or []
    if not isinstance(terms, list):
        return None
    mapped: list[dict[str, Any]] = []
    for t in terms:
        if not isinstance(t, dict):
            continue
        mapped.append(
            {
                "component_key": t.get("symbol"),
                "component_label": t.get("label"),
                "value": t.get("value"),
                "weight": t.get("weight"),
                "contribution": t.get("contribution"),
            },
        )
    return {
        "terms": mapped,
        "sum_contributions": fb.get("sum_contributions"),
        "saved_expected_sot": fb.get("stored_predicted_sot"),
        "delta": fb.get("delta_vs_stored"),
        "checksum_warning": fb.get("checksum_warning"),
    }


def _framework_consistency_side(
    *,
    active_mv: str,
    trace: list[dict[str, Any]],
    raw: dict[str, Any] | None,
    predicted: float | None,
    sum_contributions: float | None,
) -> dict[str, Any]:
    specs = manifest_for_model(active_mv)
    fw_applied = len([s for s in specs if is_countable_role(s.application_role)])
    dbg_n = len([r for r in trace if isinstance(r, dict) and is_countable_role(str(r.get("application_role") or ""))])
    val = validate_model_trace(
        active_mv,
        raw if isinstance(raw, dict) else {},
        trace,
        stored_predicted_sot=float(predicted) if predicted is not None else None,
        sum_contributions=float(sum_contributions) if sum_contributions is not None else None,
    )
    missing_data = [str(r.get("key")) for r in trace if isinstance(r, dict) and r.get("status") == "missing" and r.get("key")]
    return {
        "framework_applied_count": fw_applied,
        "debug_trace_count": dbg_n,
        "is_consistent": bool(fw_applied == dbg_n and val.get("ok")),
        "missing_trace_keys": val.get("missing_trace_keys") or [],
        "extra_trace_keys": val.get("extra_trace_keys") or [],
        "missing_data_keys": missing_data,
        "validation_warnings": val.get("warnings") or [],
    }


def build_fixture_sot_explanation(
    db: Session,
    fixture_id: int,
    *,
    model_version: str | None = None,
) -> dict[str, Any]:
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {
            "status": "missing",
            "message": "Fixture non trovata.",
            "fixture_id": int(fixture_id),
        }

    home = db.get(Team, int(fx.home_team_id))
    away = db.get(Team, int(fx.away_team_id))
    if home is None or away is None:
        return {
            "status": "missing",
            "message": "Squadre della fixture non trovate.",
            "fixture_id": int(fixture_id),
        }

    mode_audit: Literal["pre_match", "post_match"] = "post_match" if _finished(fx.status) else "pre_match"

    try:
        audit = MatchVariableAuditService().build_fixture_variables_shots_on_target(db, int(fx.id), mode=mode_audit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_fixture_sot_explanation: audit fallito (%s)", exc.__class__.__name__, exc_info=True)
        audit = None

    audit_map = _flatten_audit_variables(audit) if audit else {}

    try:
        return _build_fixture_sot_explanation_body(
            db,
            fx,
            home,
            away,
            mode_audit,
            audit_map,
            audit,
            model_version=model_version,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_fixture_sot_explanation: errore inatteso fixture_id=%s", fixture_id)
        return {
            "status": "error",
            "message": "Errore durante la costruzione della spiegazione.",
            "failed_step": "build_explanation",
            "details": f"{exc.__class__.__name__}: {exc!s}"[:800],
            "fixture_id": int(fixture_id),
            "model_version": model_version,
            "fixture": _fixture_payload(fx, home, away),
        }


def _build_fixture_sot_explanation_body(
    db: Session,
    fx: Fixture,
    home: Team,
    away: Team,
    mode_audit: Literal["pre_match", "post_match"],
    audit_map: dict[tuple[int, str], Any],
    audit: Any,
    *,
    model_version: str | None = None,
) -> dict[str, Any]:
    rows = list(db.scalars(select(TeamSotPrediction).where(TeamSotPrediction.fixture_id == int(fx.id))).all())
    preds: dict[str, dict[str, float | None]] = {}
    raw_by: dict[tuple[str, Side], dict[str, Any]] = {}
    actual_by: dict[tuple[str, Side], int | None] = {}
    for r in rows:
        mv = str(r.model_version)
        if mv not in preds:
            preds[mv] = {"home": None, "away": None}
        if int(r.team_id) == int(fx.home_team_id):
            side: Side = "home"
        elif int(r.team_id) == int(fx.away_team_id):
            side = "away"
        else:
            continue
        preds[mv][side] = float(r.predicted_sot) if r.predicted_sot is not None else None
        raw_by[(mv, side)] = r.raw_json if isinstance(r.raw_json, dict) else None
        actual_by[(mv, side)] = int(r.actual_sot) if r.actual_sot is not None else None

    active_mv: str | None = None
    if model_version:
        mvq = str(model_version).strip()
        pr = preds.get(mvq) or {}
        if pr.get("home") is not None and pr.get("away") is not None:
            active_mv = mvq
    if active_mv is None:
        active_mv = _active_model_version_from_preds(preds)
    if active_mv is None:
        return {
            "status": "missing",
            "message": "Nessuna previsione SOT salvata per questa fixture.",
            "fixture_id": int(fx.id),
            "fixture": _fixture_payload(fx, home, away),
        }

    ph = preds[active_mv].get("home")
    pa = preds[active_mv].get("away")

    row_home = next((r for r in rows if str(r.model_version) == active_mv and int(r.team_id) == int(fx.home_team_id)), None)
    row_away = next((r for r in rows if str(r.model_version) == active_mv and int(r.team_id) == int(fx.away_team_id)), None)

    raw_home = raw_by.get((active_mv, "home"))
    raw_away = raw_by.get((active_mv, "away"))

    ah = actual_by.get((active_mv, "home"))
    aa = actual_by.get((active_mv, "away"))
    played = _finished(fx.status)

    def side_summary(side: Side, name: str, pred: float | None, actual: int | None) -> dict[str, Any]:
        err = abs(float(pred) - float(actual)) if (pred is not None and actual is not None) else None
        return {
            "team_name": name,
            "predicted_sot": _round2(pred) if pred is not None else None,
            "actual_sot": actual,
            "absolute_error": _round2(err) if err is not None else None,
            "outcome_label": _outcome_sot(err) if played else None,
            "post_audit_judgment": _post_audit_judgment(err) if played else None,
        }

    prediction_summary = {
        "audit_mode": mode_audit,
        "ui_mode": "post_match_audit" if played else "pre_match",
        "home": side_summary("home", home.name, ph, ah if played else None),
        "away": side_summary("away", away.name, pa, aa if played else None),
        "match_total": {
            "predicted_sot": _round2((ph or 0) + (pa or 0)) if ph is not None and pa is not None else None,
            "actual_sot": (ah + aa) if (played and ah is not None and aa is not None) else None,
            "absolute_error": None,
        },
    }
    if (
        played
        and prediction_summary["match_total"]["predicted_sot"] is not None
        and prediction_summary["match_total"]["actual_sot"] is not None
    ):
        mt_err = abs(float(prediction_summary["match_total"]["predicted_sot"]) - float(prediction_summary["match_total"]["actual_sot"]))
        prediction_summary["match_total"]["absolute_error"] = _round2(mt_err)

    comp_home = _build_side_components(active_mv, raw_home, float(ph or 0.0))
    comp_away = _build_side_components(active_mv, raw_away, float(pa or 0.0))

    if active_mv in (BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, BASELINE_SOT_MODEL_VERSION_V10_SOT):
        _attach_samples_to_v04_variables(comp_home, int(fx.home_team_id), audit_map)
        _attach_samples_to_v04_variables(comp_away, int(fx.away_team_id), audit_map)
    elif active_mv == BASELINE_SOT_MODEL_VERSION:
        _attach_samples_v01(comp_home, int(fx.home_team_id), audit_map, fx)
        _attach_samples_v01(comp_away, int(fx.away_team_id), audit_map, fx)
    elif active_mv == BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT:
        inc_map = {
            "core_sot_component": [
                "season_avg_sot_for",
                "opponent_season_avg_sot_conceded",
                "home_avg_sot_for",
                "away_avg_sot_for",
                "home_avg_sot_conceded",
                "away_avg_sot_conceded",
            ],
            "shot_volume_component": [
                "season_avg_shots_for",
                "season_avg_shots_conceded",
                "home_avg_shots_for",
                "away_avg_shots_for",
                "home_avg_shots_conceded",
                "away_avg_shots_conceded",
            ],
            "shot_accuracy_component": ["shot_accuracy_for", "opponent_sot_allowed_ratio"],
            "recent_form_component": [
                "last5_avg_sot_for",
                "opponent_last5_avg_sot_conceded",
                "last10_avg_sot_for",
                "opponent_last10_avg_sot_conceded",
            ],
            "goals_context_component": ["season_avg_goals_for", "season_avg_goals_conceded"],
        }
        _attach_samples_v03(comp_home, int(fx.home_team_id), audit_map, inc_map)
        _attach_samples_v03(comp_away, int(fx.away_team_id), audit_map, inc_map)

    _enrich_components_with_internal_formula(active_mv, raw_home or {}, comp_home)
    _enrich_components_with_internal_formula(active_mv, raw_away or {}, comp_away)

    fb_home = _build_prediction_formula_breakdown_side(active_mv, raw_home, float(ph) if ph is not None else None)
    fb_away = _build_prediction_formula_breakdown_side(active_mv, raw_away, float(pa) if pa is not None else None)
    comparison_rows: list[dict[str, Any]] = []
    for mv, short in COMPARE_MODELS_ORDER:
        h = preds.get(mv, {}).get("home")
        a_ = preds.get(mv, {}).get("away")
        if h is None and a_ is None:
            continue
        comparison_rows.append(
            {
                "model_version": mv,
                "label": short,
                "home": _round2(h),
                "away": _round2(a_),
                "total": _round2((h + a_)) if h is not None and a_ is not None else None,
            },
        )

    deltas: list[str] = []
    v01h = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get("home")
    v01a = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get("away")
    v03h = preds.get(BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, {}).get("home")
    v03a = preds.get(BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, {}).get("away")
    v04h = preds.get(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, {}).get("home")
    v04a = preds.get(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, {}).get("away")
    if v04h is not None and v01h is not None:
        deltas.append(f"v0.4 vs v0.1 ({home.name}): {_round2(v04h - v01h):+}")
    if v04a is not None and v01a is not None:
        deltas.append(f"v0.4 vs v0.1 ({away.name}): {_round2(v04a - v01a):+}")
    if v04h is not None and v03h is not None:
        deltas.append(f"v0.4 vs v0.3 ({home.name}): {_round2(v04h - v03h):+}")
    if v04a is not None and v03a is not None:
        deltas.append(f"v0.4 vs v0.3 ({away.name}): {_round2(v04a - v03a):+}")

    v10h = preds.get(BASELINE_SOT_MODEL_VERSION_V10_SOT, {}).get("home")
    v10a = preds.get(BASELINE_SOT_MODEL_VERSION_V10_SOT, {}).get("away")
    if v10h is not None and v04h is not None:
        deltas.append(f"v1.0 vs v0.4 ({home.name}): {_round2(v10h - v04h):+}")
    if v10a is not None and v04a is not None:
        deltas.append(f"v1.0 vs v0.4 ({away.name}): {_round2(v10a - v04a):+}")

    quality_items: list[str] = []
    try:
        mc = build_model_comparison_for_fixture(db, int(fx.id), season=None, include_raw=False)
        if isinstance(mc, dict) and mc.get("status") == "success":
            diag = mc.get("diagnostics") if isinstance(mc.get("diagnostics"), dict) else {}
            for rf in diag.get("red_flags") or []:
                if isinstance(rf, str):
                    quality_items.append(rf)
            for cn in diag.get("confidence_notes") or []:
                if isinstance(cn, str):
                    quality_items.append(cn)
    except Exception:
        pass

    if active_mv in (BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, BASELINE_SOT_MODEL_VERSION_V10_SOT):
        for side_l, raw, nm in (("home", raw_home, home.name), ("away", raw_away, away.name)):
            comp = raw.get("offensive_production_component") if isinstance(raw, dict) else None
            if isinstance(comp, dict):
                if comp.get("cap_applied"):
                    quality_items.append(f"Cap applicato sulla componente offensiva ({nm}).")
                fb = comp.get("fallbacks_used")
                if isinstance(fb, list) and fb:
                    quality_items.append(f"Fallback componente offensiva ({nm}): {', '.join(str(x) for x in fb)}.")

    if active_mv == BASELINE_SOT_MODEL_VERSION_V10_SOT:
        for raw, nm in ((raw_home, home.name), (raw_away, away.name)):
            if not isinstance(raw, dict):
                continue
            formula_obj = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
            if not formula_obj.get("terms"):
                quality_items.append(
                    f"Formula terms assenti nel raw_json ({nm}). Rigenerare v1.0.",
                )
            if not isinstance(raw.get("offensive_production_component"), dict):
                quality_items.append(
                    f"Componente offensiva assente nel raw_json ({nm}). Rigenerare v1.0.",
                )
            va = raw.get("v04_alignment")
            if isinstance(va, dict) and va.get("status") == "needs_review":
                quality_items.append(
                    f"Base esplicita vs v0.4 da revisionare ({nm}): Δ {va.get('delta')}.",
                )
            xc = raw.get("xg_component")
            if isinstance(xc, dict) and xc.get("fallback_used"):
                quality_items.append(
                    f"Correzione xG non applicata ({nm}): {xc.get('fallback_reason') or 'fallback'}.",
                )

    if active_mv == BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT:
        mh = (raw_home or {}).get("meta") if isinstance(raw_home, dict) else None
        if isinstance(mh, dict) and int(mh.get("team_priors_matches_count") or 0) < 8:
            quality_items.append(f"Storico ridotto per {home.name} (partite precedenti < 8).")
        ma = (raw_away or {}).get("meta") if isinstance(raw_away, dict) else None
        if isinstance(ma, dict) and int(ma.get("team_priors_matches_count") or 0) < 8:
            quality_items.append(f"Storico ridotto per {away.name} (partite precedenti < 8).")

    if v04h is not None and v01h is not None and (v04h - v01h) <= -0.75:
        quality_items.append(f"v0.4 riduce {home.name} di {v04h - v01h:.2f} rispetto a v0.1.")
    if v04a is not None and v01a is not None and (v04a - v01a) <= -0.75:
        quality_items.append(f"v0.4 riduce {away.name} di {v04a - v01a:.2f} rispetto a v0.1.")

    # Player impact non applicato alla baseline numerica
    if active_mv == BASELINE_SOT_MODEL_VERSION:
        quality_items.append("Player impact non applicato alla formula baseline v0.1.")

    human = _human_summary(
        home_name=home.name,
        away_name=away.name,
        ph=ph,
        pa=pa,
        row_h=row_home,
        row_a=row_away,
        raw_h=raw_home if isinstance(raw_home, dict) else None,
        raw_a=raw_away if isinstance(raw_away, dict) else None,
    )

    variables_used_home: list[dict[str, Any]] = []
    variables_used_away: list[dict[str, Any]] = []
    for comp in comp_home:
        for v in comp.get("variables") or []:
            if isinstance(v, dict):
                variables_used_home.append({**v, "parent_component_id": comp.get("id")})
    for comp in comp_away:
        for v in comp.get("variables") or []:
            if isinstance(v, dict):
                variables_used_away.append({**v, "parent_component_id": comp.get("id")})

    h_to_ko = compute_hours_to_kickoff(fx.kickoff_at if isinstance(fx.kickoff_at, datetime) else None)
    conf_h = int(row_home.confidence_score) if row_home and row_home.confidence_score is not None else None
    conf_a = int(row_away.confidence_score) if row_away and row_away.confidence_score is not None else None

    trace_home = build_applied_variable_trace_side(
        active_mv,
        raw_home if isinstance(raw_home, dict) else {},
        team_id=int(fx.home_team_id),
        team_name=home.name,
        audit_map=audit_map,
        hours_to_kickoff=h_to_ko,
        prediction_confidence=conf_h,
    )
    trace_away = build_applied_variable_trace_side(
        active_mv,
        raw_away if isinstance(raw_away, dict) else {},
        team_id=int(fx.away_team_id),
        team_name=away.name,
        audit_map=audit_map,
        hours_to_kickoff=h_to_ko,
        prediction_confidence=conf_a,
    )

    sum_c_home = float(fb_home["sum_contributions"]) if isinstance(fb_home, dict) and fb_home.get("sum_contributions") is not None else None
    sum_c_away = float(fb_away["sum_contributions"]) if isinstance(fb_away, dict) and fb_away.get("sum_contributions") is not None else None

    fw_cons_home = _framework_consistency_side(
        active_mv=active_mv,
        trace=trace_home,
        raw=raw_home if isinstance(raw_home, dict) else None,
        predicted=float(ph) if ph is not None else None,
        sum_contributions=sum_c_home,
    )
    fw_cons_away = _framework_consistency_side(
        active_mv=active_mv,
        trace=trace_away,
        raw=raw_away if isinstance(raw_away, dict) else None,
        predicted=float(pa) if pa is not None else None,
        sum_contributions=sum_c_away,
    )

    remediation_hints: dict[str, list[str]] | None = None
    if active_mv == BASELINE_SOT_MODEL_VERSION_V11_SOT:
        sy = _fixture_season_year(db, fx)
        rh_home = _v11_shot_coverage_remediation_hints(
            raw=raw_home if isinstance(raw_home, dict) else None,
            season_year=sy,
        )
        rh_away = _v11_shot_coverage_remediation_hints(
            raw=raw_away if isinstance(raw_away, dict) else None,
            season_year=sy,
        )
        if rh_home or rh_away:
            remediation_hints = {"home": rh_home, "away": rh_away}

    return {
        "status": "ok",
        "fixture": _fixture_payload(fx, home, away),
        "market": "shots_on_target",
        "active_model_version": active_mv,
        "framework_consistency": {
            "model_version": active_mv,
            "home": fw_cons_home,
            "away": fw_cons_away,
        },
        "prediction_summary": prediction_summary,
        "final_formula": {
            "formula_label": "expected_sot: mix pesato (v0.1/v0.3/v0.4) o somma additiva (v0.2) — vedi terms",
            "home": _build_final_formula_side(fb_home if isinstance(fb_home, dict) else None),
            "away": _build_final_formula_side(fb_away if isinstance(fb_away, dict) else None),
        },
        "component_tree": {
            "home": _build_component_tree_side(comp_home),
            "away": _build_component_tree_side(comp_away),
        },
        "applied_variable_trace": {"home": trace_home, "away": trace_away},
        "not_applied_variables": {
            "items": [],
            "note": "Variabili del Framework non incluse nel modello attivo: consulta Framework Analisi con filtro per model_version.",
        },
        "actual_result": {
            "fixture_finished": played,
            "home_actual_sot": ah if played else None,
            "away_actual_sot": aa if played else None,
        },
        "model_comparison": {
            "rows": comparison_rows,
            "deltas_text": deltas,
        },
        "components": {"home": comp_home, "away": comp_away},
        "prediction_formula_breakdown": {"home": fb_home, "away": fb_away},
        "variables_used": {"home": variables_used_home, "away": variables_used_away},
        "quality_checks": {
            "status": "warnings" if quality_items else "ok",
            "items": quality_items or ["Nessuna red flag rilevante."],
        },
        "human_summary": human,
        "remediation_hints": remediation_hints,
        "technical_audit": {
            "prediction_raw_json": {
                "home": raw_home,
                "away": raw_away,
            },
            "data_policy": (
                audit.data_policy.model_dump(mode="json")
                if audit is not None and getattr(audit, "data_policy", None) is not None
                else None
            ),
        },
    }


def _fixture_payload(fx: Fixture, home: Team, away: Team) -> dict[str, Any]:
    return {
        "fixture_id": int(fx.id),
        "api_fixture_id": int(fx.api_fixture_id),
        "round": fx.round,
        "kickoff_at": fx.kickoff_at.isoformat() if isinstance(fx.kickoff_at, datetime) else str(fx.kickoff_at),
        "status_short": fx.status,
        "home_team": {"id": int(fx.home_team_id), "name": home.name, "logo_url": home.logo_url},
        "away_team": {"id": int(fx.away_team_id), "name": away.name, "logo_url": away.logo_url},
    }
