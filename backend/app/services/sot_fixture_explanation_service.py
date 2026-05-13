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
    FINISHED_STATUSES,
)
from app.models import Fixture, Team, TeamSotPrediction
from app.schemas.match_analysis import MatchVariablesAuditResponse
from app.services.debug_sot_model_comparison import build_model_comparison_for_fixture
from app.services.match_variable_audit_service import MatchVariableAuditService
from app.services.sot_prediction_service import WEIGHTS_BASELINE_V0_1

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
]


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
    for mv in (
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
        BASELINE_SOT_MODEL_VERSION_V02,
        BASELINE_SOT_MODEL_VERSION,
    ):
        row = preds.get(mv) or {}
        if row.get("home") is not None and row.get("away") is not None:
            return mv
    for mv, row in preds.items():
        if row.get("home") is not None or row.get("away") is not None:
            return mv
    return None


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
    if model_version in (BASELINE_SOT_MODEL_VERSION_V02, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED):
        return _components_v02(raw, predicted)
    return []


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


def build_fixture_sot_explanation(db: Session, fixture_id: int) -> dict[str, Any]:
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

    if active_mv == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
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

    # Confronto modelli compatto
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

    if active_mv == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
        for side_l, raw, nm in (("home", raw_home, home.name), ("away", raw_away, away.name)):
            comp = raw.get("offensive_production_component") if isinstance(raw, dict) else None
            if isinstance(comp, dict):
                if comp.get("cap_applied"):
                    quality_items.append(f"Cap applicato sulla componente offensiva ({nm}).")
                fb = comp.get("fallbacks_used")
                if isinstance(fb, list) and fb:
                    quality_items.append(f"Fallback componente offensiva ({nm}): {', '.join(str(x) for x in fb)}.")

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

    return {
        "status": "ok",
        "fixture": _fixture_payload(fx, home, away),
        "market": "shots_on_target",
        "active_model_version": active_mv,
        "prediction_summary": prediction_summary,
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
        "variables_used": {"home": variables_used_home, "away": variables_used_away},
        "quality_checks": {
            "status": "warnings" if quality_items else "ok",
            "items": quality_items or ["Nessuna red flag rilevante."],
        },
        "human_summary": human,
        "technical_audit": {
            "prediction_raw_json": {
                "home": raw_home,
                "away": raw_away,
            },
            "data_policy": audit.data_policy.model_dump(mode="json") if audit else None,
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
