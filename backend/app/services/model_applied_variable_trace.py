"""
Costruzione applied_variable_trace e validazione coerenza (solo lettura / serializzazione).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
from app.services.model_applied_variable_manifest import (
    AppliedVariableSpec,
    is_countable_role,
    manifest_for_model,
)
from app.services.predictions_v10.offensive_production_blend import INPUT_LABELS, offensive_inputs_as_map
from app.services.sot_model_constants import WEIGHTS_BASELINE_V0_1

CHECKSUM_TOLERANCE = 0.02
CHECKSUM_WARNING_IT = (
    "La somma dei contributi non coincide perfettamente con la prediction salvata. "
    "Possibili arrotondamenti, cap o fallback."
)

logger = logging.getLogger(__name__)


def _sf(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return v


def _r2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _audit_val(audit_map: dict[tuple[int, str], Any], team_id: int, audit_key: str) -> Any:
    row = audit_map.get((int(team_id), audit_key))
    if not isinstance(row, dict):
        return None
    calc = row.get("calculation")
    if isinstance(calc, dict) and calc.get("value") is not None:
        return calc.get("value")
    return row.get("display_value")


def _audit_formula(audit_map: dict[tuple[int, str], Any], team_id: int, audit_key: str) -> str | None:
    row = audit_map.get((int(team_id), audit_key))
    if not isinstance(row, dict):
        return None
    calc = row.get("calculation")
    if isinstance(calc, dict) and isinstance(calc.get("formula"), str):
        return calc.get("formula")
    return None


def _audit_source(audit_map: dict[tuple[int, str], Any], team_id: int, audit_key: str) -> str | None:
    row = audit_map.get((int(team_id), audit_key))
    if not isinstance(row, dict):
        return None
    if isinstance(row.get("source_description"), str):
        return row.get("source_description")
    return str(row.get("source_table") or "audit_variabili")


def _row_for_spec(
    spec: AppliedVariableSpec,
    *,
    model_version: str,
    raw: dict[str, Any] | None,
    team_id: int,
    team_name: str,
    audit_map: dict[tuple[int, str], Any],
    hours_to_kickoff: float | None,
    pred_confidence: int | None,
) -> dict[str, Any]:
    raw = raw or {}
    key_out = spec.framework_key or spec.trace_key
    base: dict[str, Any] = {
        "key": key_out,
        "trace_key": spec.trace_key,
        "label": spec.label,
        "area": spec.area,
        "application_role": spec.application_role,
        "parent_component": spec.parent_component,
        "team_id": int(team_id),
        "team_name": team_name,
        "value": None,
        "unit": None,
        "weight": None,
        "contribution": None,
        "formula": None,
        "source": f"team_sot_predictions.raw_json ({model_version})",
        "matches_count": None,
        "sample_rows_count": None,
        "fallback_used": False,
        "cap_applied": False,
        "notes": None,
        "status": "available",
        "model_version": model_version,
    }

    r = spec.resolver

    if r.startswith("v01_factor:"):
        fk = r.split(":", 1)[1]
        wmap = raw.get("weights") if isinstance(raw.get("weights"), dict) else {}
        resolved = raw.get("resolved_inputs") if isinstance(raw.get("resolved_inputs"), dict) else {}
        inputs = raw.get("inputs") if isinstance(raw.get("inputs"), dict) else {}
        w = _sf(wmap.get(fk)) or _sf(WEIGHTS_BASELINE_V0_1.get(fk))
        val = _sf(resolved.get(fk))
        base["value"] = _r2(val)
        base["weight"] = w
        if w is not None and val is not None:
            base["contribution"] = _r2(float(val) * float(w))
        base["unit"] = "tiri in porta"
        base["formula"] = f"resolved({fk}) × peso"
        base["fallback_used"] = bool(inputs.get(fk) is None)
        base["status"] = "fallback" if base["fallback_used"] else "available"
        if base["fallback_used"]:
            base["notes"] = "Input grezzo assente: usato valore risolto (fallback)."
        return base

    if r == "v01_quality:confidence_score":
        base["value"] = float(pred_confidence) if pred_confidence is not None else None
        base["unit"] = "score 0-100"
        base["source"] = "team_sot_predictions.confidence_score"
        base["formula"] = "euristica da feature row (v0.1)"
        if base["value"] is None:
            base["status"] = "missing"
        return base

    if r == "v02:baseline":
        base["value"] = _r2(_sf(raw.get("baseline_expected_sot")))
        base["contribution"] = base["value"]
        base["unit"] = "tiri in porta"
        base["formula"] = "baseline v0.1 attesa"
        if base["value"] is None:
            base["status"] = "missing"
        return base

    if r.startswith("v02:adjustment:"):
        k = r.split(":")[-1]
        bd = raw.get("adjustment_breakdown") if isinstance(raw.get("adjustment_breakdown"), dict) else {}
        sub = bd.get(k) if isinstance(bd.get(k), dict) else {}
        if not sub and k == "player" and isinstance(bd.get("player_adjustment"), dict):
            sub = bd["player_adjustment"]
        delta = _sf(sub.get("adjustment")) or _sf(sub.get("delta"))
        if delta is None:
            root_map = {
                "player": "player_adjustment",
                "h2h": "h2h_adjustment",
                "motivation": "motivation_adjustment",
                "availability": "availability_adjustment",
            }
            rk = root_map.get(k)
            if rk:
                delta = _sf(raw.get(rk))
        if delta is None:
            delta = 0.0
        base["value"] = _r2(delta)
        base["contribution"] = base["value"]
        base["unit"] = "delta SOT"
        base["formula"] = str(sub.get("details") or sub.get("explanation") or f"adjustment:{k}")
        base["status"] = "available"
        return base

    if r == "v02:quality:confidence_v02":
        base["value"] = _sf(raw.get("prediction_confidence_score_v0_2"))
        if base["value"] is None:
            base["value"] = float(pred_confidence) if pred_confidence is not None else None
        base["unit"] = "score"
        base["source"] = "raw_json.prediction_confidence_score_v0_2"
        base["formula"] = str(raw.get("prediction_confidence_label_v0_2") or "")
        if base["value"] is None:
            base["status"] = "missing"
        return base

    if r.startswith("v03:component:"):
        comp_key = r.split(":")[-1]
        comps = raw.get("components") if isinstance(raw.get("components"), dict) else {}
        wmap = raw.get("weights") if isinstance(raw.get("weights"), dict) else {}
        cobj = comps.get(comp_key) if isinstance(comps, dict) else None
        val = _sf((cobj or {}).get("value")) if isinstance(cobj, dict) else None
        w = _sf(wmap.get(comp_key))
        base["value"] = _r2(val)
        base["weight"] = w
        if w is not None and val is not None:
            base["contribution"] = _r2(float(val) * float(w))
        base["unit"] = "tiri in porta (scala componente)"
        base["formula"] = str((cobj or {}).get("formula") or "") if isinstance(cobj, dict) else None
        if val is None:
            base["status"] = "missing"
        return base

    if r.startswith("v03:input:"):
        parts = r.split(":")
        comp_key = parts[2] if len(parts) > 2 else ""
        ik = parts[3] if len(parts) > 3 else ""
        inputs = raw.get("inputs") if isinstance(raw.get("inputs"), dict) else {}
        resolved = raw.get("resolved_inputs") if isinstance(raw.get("resolved_inputs"), dict) else {}
        fallbacks = raw.get("fallbacks") if isinstance(raw.get("fallbacks"), dict) else {}
        iv = _sf(inputs.get(ik))
        rv = _sf(resolved.get(ik))
        base["value"] = _r2(rv if rv is not None else iv)
        base["unit"] = "misto"
        fb = bool(fallbacks.get(ik)) if isinstance(fallbacks, dict) else False
        base["fallback_used"] = fb
        base["formula"] = f"inputs/resolved[{ik}]"
        base["status"] = "fallback" if fb else ("missing" if base["value"] is None else "available")
        if fb and isinstance(fallbacks.get(ik), str):
            base["notes"] = str(fallbacks.get(ik))
        return base

    if r == "v03:quality:team_priors_matches_count":
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        base["value"] = _sf(meta.get("team_priors_matches_count"))
        base["unit"] = "partite"
        base["formula"] = "raw_json.meta.team_priors_matches_count"
        if base["value"] is None:
            base["status"] = "missing"
        return base

    if r.startswith("v10:formula_term:"):
        term = r.split(":")[-1]
        formula_obj = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
        terms_list = formula_obj.get("terms") if isinstance(formula_obj.get("terms"), list) else []
        ft = next((t for t in terms_list if isinstance(t, dict) and str(t.get("key") or "") == term), None)
        if ft:
            base["value"] = _r2(_sf(ft.get("value")))
            base["weight"] = _sf(ft.get("weight"))
            base["contribution"] = _r2(_sf(ft.get("contribution")))
            sp = ft.get("source_path") or ft.get("source")
            base["source"] = str(sp) if sp else base["source"]
            base["fallback_used"] = bool(ft.get("fallback_used"))
            base["status"] = str(ft.get("status") or ("fallback" if base["fallback_used"] else "available"))
            base["formula"] = str(ft.get("formula") or base["formula"])
            base["unit"] = "xG medi" if term == "expected_goals" else "tiri in porta"
            return base
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        if term == "offensive_production_component":
            ov = _sf(comp.get("value"))
            ow = _sf(comp.get("weight_in_final_formula")) or _sf(comp.get("weight_in_model")) or 0.30
            base["value"] = _r2(ov)
            base["weight"] = ow
            base["contribution"] = _r2(_sf(comp.get("contribution_in_final_formula")))
            if base["contribution"] is None and ov is not None and ow is not None:
                base["contribution"] = _r2(float(ov) * float(ow))
            base["unit"] = "tiri in porta"
            base["formula"] = str(comp.get("formula") or "Produzione offensiva composita × 0.30")
            base["fallback_used"] = bool(comp.get("fallbacks_used"))
            base["status"] = "fallback" if base["fallback_used"] else "available"
            return base
        base["status"] = "missing"
        return base

    if r.startswith("v10:offensive_input:"):
        ik = r.split(":")[-1]
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        blob = offensive_inputs_as_map(comp).get(ik)
        if blob is None:
            base["status"] = "missing"
            base["notes"] = "Chiave assente in offensive_production_component.inputs"
            return base
        base["value"] = _r2(_sf(blob.get("normalized_value") if blob.get("normalized_value") is not None else blob.get("value")))
        base["weight"] = _sf(blob.get("internal_weight") if blob.get("internal_weight") is not None else blob.get("weight"))
        base["contribution"] = _r2(_sf(blob.get("internal_contribution") if blob.get("internal_contribution") is not None else blob.get("contribution")))
        rv = _sf(blob.get("raw_value"))
        if rv is not None:
            base["notes"] = f"valore grezzo: {_r2(rv)}"
        base["unit"] = "scala SOT"
        base["formula"] = str(blob.get("formula") or INPUT_LABELS.get(ik, ik))
        base["matches_count"] = blob.get("sample_count") if blob.get("sample_count") is not None else blob.get("matches_count")
        base["fallback_used"] = bool(blob.get("fallback_used"))
        base["cap_applied"] = False
        sp = blob.get("source_path") or blob.get("source_table")
        base["source"] = str(sp) if sp else "fixture_team_stats"
        base["status"] = "fallback" if base["fallback_used"] else "available"
        return base

    if r == "v10:quality:offensive_component":
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        q = comp.get("quality") if isinstance(comp.get("quality"), dict) else {}
        base["value"] = _sf(q.get("inputs_available"))
        base["unit"] = "conteggio"
        base["formula"] = (
            f"inputs_total={q.get('inputs_total')}; fallback_count={q.get('fallback_count')}; "
            f"missing={q.get('missing_inputs')}"
        )
        base["fallback_used"] = int(q.get("fallback_count") or 0) > 0
        base["status"] = "fallback" if base["fallback_used"] else "available"
        return base

    if r.startswith("v11:formula_term:"):
        term = r.split(":")[-1]
        formula_obj = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
        terms_list = formula_obj.get("terms") if isinstance(formula_obj.get("terms"), list) else []
        ft = next((t for t in terms_list if isinstance(t, dict) and str(t.get("key") or "") == term), None)
        if ft:
            base["value"] = _r2(_sf(ft.get("value")))
            base["weight"] = _sf(ft.get("weight"))
            base["contribution"] = _r2(_sf(ft.get("contribution")))
            base["unit"] = "tiri in porta"
            base["status"] = str(ft.get("status") or "available")
            base["fallback_used"] = False
            return base
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        if term == "offensive_production_component" and comp:
            ov = _sf(comp.get("value"))
            base["value"] = _r2(ov)
            base["weight"] = 1.0
            base["contribution"] = _r2(ov)
            base["unit"] = "tiri in porta"
            base["fallback_used"] = False
            base["status"] = "available" if raw.get("prediction_valid", True) else "missing"
            return base
        base["status"] = "missing"
        return base

    if r.startswith("v11:offensive_input:"):
        ik = r.split(":")[-1]
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        blob = offensive_inputs_as_map(comp).get(ik)
        if blob is None:
            base["status"] = "missing"
            base["notes"] = "Chiave assente in offensive_production_component.inputs"
            return base
        base["value"] = _r2(_sf(blob.get("normalized_value") if blob.get("normalized_value") is not None else blob.get("value")))
        base["weight"] = _sf(blob.get("internal_weight") if blob.get("internal_weight") is not None else blob.get("weight"))
        base["contribution"] = _r2(_sf(blob.get("internal_contribution") if blob.get("internal_contribution") is not None else blob.get("contribution")))
        rv = _sf(blob.get("raw_value"))
        if rv is not None:
            base["notes"] = f"valore grezzo: {_r2(rv)}"
        base["unit"] = "scala SOT"
        base["matches_count"] = blob.get("sample_count") if blob.get("sample_count") is not None else blob.get("matches_count")
        base["fallback_used"] = False
        sp = blob.get("source_path") or blob.get("db_field")
        base["source"] = str(sp) if sp else "fixture_team_stats"
        base["status"] = str(blob.get("status") or "available")
        return base

    if r == "v11:quality:offensive_component":
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        q = comp.get("quality") if isinstance(comp.get("quality"), dict) else {}
        base["value"] = _sf(q.get("inputs_available"))
        base["unit"] = "conteggio"
        base["formula"] = (
            f"inputs_total={q.get('inputs_total')}; fallback_count={q.get('fallback_count')}; "
            f"missing={q.get('missing_required')}"
        )
        base["fallback_used"] = False
        base["status"] = "available" if int(q.get("fallback_count") or 0) == 0 else "missing"
        return base

    if r.startswith("v04:formula_term:"):
        term = r.split(":")[-1]
        arch = str(raw.get("architecture") or "")
        formula_obj = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
        terms_list = formula_obj.get("terms") if isinstance(formula_obj.get("terms"), list) else []
        if (
            arch.startswith("feature_registry")
            or arch in ("explicit_terms_from_v04_plus_xg", "explicit_terms_from_v04")
        ) and terms_list:
            ft = next((t for t in terms_list if isinstance(t, dict) and str(t.get("key") or "") == term), None)
            if ft:
                base["value"] = _r2(_sf(ft.get("value")))
                base["weight"] = _sf(ft.get("weight"))
                base["contribution"] = _r2(_sf(ft.get("contribution")))
                sp = ft.get("source_path") or ft.get("source")
                base["source"] = str(sp) if sp else base["source"]
                base["fallback_used"] = bool(ft.get("fallback_used"))
                base["status"] = str(ft.get("status") or ("fallback" if base["fallback_used"] else "available"))
                base["formula"] = str(ft.get("formula") or base["formula"])
                fr = ft.get("fallback_reason")
                base["notes"] = str(fr) if fr else base["notes"]
                base["unit"] = "xG medi" if term == "expected_goals" else "tiri in porta"
                base["cap_applied"] = bool(ft.get("cap_applied"))
                return base
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        dbg = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
        bo = dbg.get("baseline_other_inputs") if isinstance(dbg.get("baseline_other_inputs"), dict) else {}
        if term == "offensive_production_component":
            ov = _sf(comp.get("value"))
            ow = _sf(comp.get("weight_in_model")) or 0.30
            base["value"] = _r2(ov)
            base["weight"] = ow
            if ov is not None and ow is not None:
                base["contribution"] = _r2(float(ov) * float(ow))
            base["unit"] = "tiri in porta"
            base["formula"] = "componente offensiva × peso nel mix v0.4"
            base["cap_applied"] = bool(comp.get("cap_applied"))
            base["fallback_used"] = bool(comp.get("fallbacks_used"))
            if base["value"] is None:
                base["status"] = "missing"
            return base
        w_by = {
            "opp_avg_sot_conceded": 0.25,
            "team_split_avg_sot_for": 0.15,
            "opp_split_avg_sot_conceded": 0.10,
            "team_last5_avg_sot_for": 0.10,
            "opp_last5_avg_sot_conceded": 0.10,
        }
        w = w_by.get(term)
        val = _sf(bo.get(term))
        base["value"] = _r2(val)
        base["weight"] = w
        if val is not None and w is not None:
            base["contribution"] = _r2(float(val) * float(w))
        base["unit"] = "tiri in porta"
        base["formula"] = f"debug.baseline_other_inputs[{term}] × {w}"
        if val is None:
            base["status"] = "missing"
        return base

    if r.startswith("v04:offensive_input:"):
        ik = r.split(":")[-1]
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        blob = offensive_inputs_as_map(comp).get(ik)
        if blob is None:
            base["status"] = "missing"
            base["notes"] = "Chiave assente in offensive_production_component.inputs"
            return base
        base["value"] = _r2(_sf(blob.get("value")))
        base["weight"] = _sf(blob.get("weight"))
        base["contribution"] = _r2(_sf(blob.get("contribution")))
        if base["contribution"] is None and base["value"] is not None and base["weight"] is not None:
            base["contribution"] = _r2(float(base["value"]) * float(base["weight"]))
        base["unit"] = str(blob.get("unit") or "misto")
        base["formula"] = str(blob.get("formula") or blob.get("description") or "")
        base["matches_count"] = blob.get("matches_count")
        base["sample_rows_count"] = blob.get("sample_rows_count")
        fb_list = comp.get("fallbacks_used") if isinstance(comp.get("fallbacks_used"), list) else []
        base["fallback_used"] = ik in [str(x) for x in fb_list]
        base["cap_applied"] = bool(comp.get("cap_applied"))
        sp = blob.get("source_path") or blob.get("source_table")
        base["source"] = str(sp) if sp else "fixture_team_stats / fixtures"
        st = blob.get("status")
        base["status"] = str(st) if st else ("fallback" if base["fallback_used"] else "available")
        return base

    if r == "v04:quality:cap":
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        dbg = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
        base["value"] = 1.0 if comp.get("cap_applied") else 0.0
        base["unit"] = "flag"
        base["formula"] = f"cap_applied={bool(comp.get('cap_applied'))}; raw={dbg.get('raw_component_value')}; bounds={dbg.get('cap_bounds')}"
        base["cap_applied"] = bool(comp.get("cap_applied"))
        return base

    if r == "v04:quality:fallbacks":
        comp = raw.get("offensive_production_component") if isinstance(raw.get("offensive_production_component"), dict) else {}
        fb = comp.get("fallbacks_used") if isinstance(comp.get("fallbacks_used"), list) else []
        base["value"] = ", ".join(str(x) for x in fb) if fb else None
        base["unit"] = "lista"
        base["fallback_used"] = bool(fb)
        base["formula"] = "offensive_production_component.fallbacks_used"
        base["status"] = "fallback" if fb else "available"
        return base

    if r == "v04:quality:row_confidence":
        base["value"] = float(pred_confidence) if pred_confidence is not None else None
        base["unit"] = "score"
        base["source"] = "team_sot_predictions.confidence_score"
        if base["value"] is None:
            base["status"] = "missing"
        return base

    if r.startswith("audit:"):
        ak = r.split(":", 1)[1]
        av = _audit_val(audit_map, team_id, ak)
        base["value"] = av if isinstance(av, (int, float)) else (av if av is not None else None)
        base["unit"] = "testo / misto"
        base["formula"] = _audit_formula(audit_map, team_id, ak)
        base["source"] = _audit_source(audit_map, team_id, ak) or "match_variable_audit"
        if av is None:
            base["status"] = "missing"
            base["notes"] = "Variabile di contesto non presente nell'audit per questa fixture/squadra."
        return base

    if r == "fixture:hours_to_kickoff":
        base["value"] = _r2(hours_to_kickoff) if hours_to_kickoff is not None else None
        base["unit"] = "ore"
        base["source"] = "fixture.kickoff_at vs now (UTC)"
        base["formula"] = "(kickoff - now) in ore"
        if base["value"] is None:
            base["status"] = "missing"
        return base

    if r == "v10:xg_component:expected_goals":
        xc = raw.get("xg_component") if isinstance(raw.get("xg_component"), dict) else {}
        formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
        terms = formula.get("terms") if isinstance(formula.get("terms"), list) else []
        xg_term = next((t for t in terms if isinstance(t, dict) and t.get("key") == "expected_goals"), None)
        contrib = _r2(_sf((xg_term or {}).get("contribution"))) if xg_term else _r2(_sf(xc.get("xg_adjustment_sot")))
        base["value"] = _r2(_sf(xc.get("team_avg_xg_for")))
        base["weight"] = _sf(xc.get("xg_sensitivity")) or 0.10
        base["contribution"] = contrib if contrib is not None else 0.0
        base["formula"] = (
            "correzione esplicita basata su xG prodotti e xG concessi dall'avversario "
            "(base_explicit_sot * xg_adjustment_pct)"
        )
        base["source"] = str(xc.get("source") or "fixtures/statistics::expected_goals")
        base["unit"] = "xG medi"
        base["cap_applied"] = bool(xc.get("cap_applied"))
        fb = bool(xc.get("fallback_used")) or not bool(xc.get("xg_adjustment_applied"))
        base["fallback_used"] = fb
        if fb or not bool(xc.get("xg_available")):
            base["status"] = "fallback"
            base["notes"] = str(xc.get("fallback_reason") or "") or None
        else:
            base["status"] = "available"
            base["notes"] = (
                "Dato diretto API-Football. Usato per stimare la qualità delle occasioni e correggere "
                "in modo prudente la previsione tiri in porta."
            )
        return base

    base["status"] = "missing"
    base["notes"] = f"Resolver non gestito: {r}"
    return base


def build_applied_variable_trace_side(
    model_version: str,
    raw: dict[str, Any] | None,
    *,
    team_id: int,
    team_name: str,
    audit_map: dict[tuple[int, str], Any],
    hours_to_kickoff: float | None,
    prediction_confidence: int | None,
) -> list[dict[str, Any]]:
    specs = manifest_for_model(model_version)
    return [
        _row_for_spec(
            sp,
            model_version=model_version,
            raw=raw if isinstance(raw, dict) else {},
            team_id=team_id,
            team_name=team_name,
            audit_map=audit_map,
            hours_to_kickoff=hours_to_kickoff,
            pred_confidence=prediction_confidence,
        )
        for sp in specs
    ]


def compute_hours_to_kickoff(kickoff_at: datetime | None) -> float | None:
    if kickoff_at is None:
        return None
    ko = kickoff_at
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    delta = ko - datetime.now(timezone.utc)
    return round(delta.total_seconds() / 3600.0, 2)


def validate_model_trace(
    model_version: str,
    raw: dict[str, Any] | None,
    trace: list[dict[str, Any]],
    *,
    stored_predicted_sot: float | None,
    sum_contributions: float | None,
) -> dict[str, Any]:
    specs = manifest_for_model(model_version)
    expected_keys = {s.trace_key for s in specs}
    got_keys = {str(x.get("trace_key")) for x in trace if isinstance(x, dict) and x.get("trace_key")}
    missing = sorted(expected_keys - got_keys)
    extra = sorted(got_keys - {s.trace_key for s in specs})
    warnings: list[str] = []
    if missing:
        warnings.append(f"Trace incompleto: mancano chiavi manifest {missing[:12]}{'…' if len(missing) > 12 else ''}")
    if extra:
        warnings.append(f"Trace con chiavi extra rispetto al manifest: {extra[:12]}")

    if (
        model_version == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
        and stored_predicted_sot is not None
        and sum_contributions is not None
        and abs(float(sum_contributions) - float(stored_predicted_sot)) > CHECKSUM_TOLERANCE
    ):
        comp = (raw or {}).get("offensive_production_component") if isinstance(raw, dict) else None
        cap = bool((comp or {}).get("cap_applied")) if isinstance(comp, dict) else False
        if not cap:
            warnings.append(CHECKSUM_WARNING_IT)

    if warnings:
        for w in warnings:
            logger.warning("validate_model_trace [%s]: %s", model_version, w)

    return {
        "ok": not missing and not extra and len(warnings) == 0,
        "warnings": warnings,
        "missing_trace_keys": missing,
        "extra_trace_keys": extra,
    }


def append_trace_to_raw_json(
    raw: dict[str, Any],
    *,
    model_version: str,
    team_id: int,
    team_name: str,
    audit_map: dict[tuple[int, str], Any],
    hours_to_kickoff: float | None,
    prediction_confidence: int | None,
) -> dict[str, Any]:
    """Aggiunge applied_variable_trace al dict raw_json prima del salvataggio (nessun ricalcolo numerico)."""
    trace = build_applied_variable_trace_side(
        model_version,
        raw,
        team_id=team_id,
        team_name=team_name,
        audit_map=audit_map,
        hours_to_kickoff=hours_to_kickoff,
        prediction_confidence=prediction_confidence,
    )
    out = dict(raw)
    out["applied_variable_trace"] = trace
    return out
