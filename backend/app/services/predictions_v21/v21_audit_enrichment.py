"""Enrichment audit-only del raw_json v2.1 (non modifica prediction salvate)."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.services.predictions_v21.v21_constants import PREDICTIVE_MACRO_KEYS, QUALITY_MACRO_KEY
from app.services.predictions_v21.v21_xg_coverage import XG_MISSING_WARNING, competition_has_xg_in_team_stats

XG_MICRO_KEYS = frozenset(
    {
        "xg_produced",
        "xg_conceded_by_opponent",
        "xg_delta_vs_league",
        "opp_xg_conceded_delta",
        "xg_prudent_adjustment",
    }
)

FEED_UNAVAILABLE_SOURCE = "feed_unavailable.xg"
CHANCE_QUALITY_MACRO_WARNING = "Macroarea neutralizzata: dati xG non disponibili nel feed."


def _is_xg_feed_unavailable(raw: dict[str, Any], db: Session | None, competition_id: int | None) -> bool:
    warnings = raw.get("warnings") if isinstance(raw.get("warnings"), list) else []
    if any(XG_MISSING_WARNING in str(w) for w in warnings):
        return True
    if db is not None and competition_id is not None:
        return not competition_has_xg_in_team_stats(db, int(competition_id))
    components = raw.get("components") if isinstance(raw.get("components"), dict) else {}
    cq = components.get("chance_quality") if isinstance(components.get("chance_quality"), dict) else {}
    inputs = cq.get("inputs") if isinstance(cq.get("inputs"), dict) else {}
    if not inputs:
        return False
    xg_inputs = [inputs[k] for k in XG_MICRO_KEYS if k in inputs and isinstance(inputs[k], dict)]
    if not xg_inputs:
        return False
    return all(
        str(inp.get("status") or "") in ("missing", "feed_unavailable")
        and (
            XG_MISSING_WARNING in str(inp.get("warning") or "")
            or inp.get("raw_value") is None
        )
        for inp in xg_inputs
    )


def _patch_micro_input(inp: dict[str, Any], *, feed_unavailable: bool) -> dict[str, Any]:
    out = dict(inp)
    if feed_unavailable:
        out["status"] = "feed_unavailable"
        out["source_path"] = FEED_UNAVAILABLE_SOURCE
        out["raw_value"] = None
        out["value"] = None
        out["normalized_value"] = round(float(out.get("normalized_value") or 1.0), 2)
        out["fallback_used"] = True
        out["contribution"] = "neutra"
        out["warning"] = XG_MISSING_WARNING
    elif str(out.get("status") or "") == "missing" and out.get("normalized_value") == 1.0:
        if out.get("fallback_used"):
            out["status"] = "feed_unavailable" if "xG" in str(out.get("warning") or "") else out.get("status")
    return out


def _patch_macro_component(comp: dict[str, Any], *, macro_key: str, feed_unavailable: bool) -> dict[str, Any]:
    out = dict(comp)
    inputs = out.get("inputs") if isinstance(out.get("inputs"), dict) else {}
    patched_inputs: dict[str, Any] = {}
    for mk, inp in inputs.items():
        if not isinstance(inp, dict):
            patched_inputs[mk] = inp
            continue
        is_xg = mk in XG_MICRO_KEYS
        patched_inputs[mk] = _patch_micro_input(inp, feed_unavailable=feed_unavailable and is_xg)

    out["inputs"] = patched_inputs

    if macro_key == "chance_quality" and feed_unavailable:
        micro_statuses = [
            str(patched_inputs[k].get("status") or "")
            for k in XG_MICRO_KEYS
            if k in patched_inputs and isinstance(patched_inputs[k], dict)
        ]
        if micro_statuses and all(s == "feed_unavailable" for s in micro_statuses):
            out["status"] = "degraded_feed_unavailable"
            out["coverage_pct"] = 0.0
            out["macro_index"] = round(float(out.get("macro_index") or out.get("value") or 1.0), 4)
            out["value"] = out["macro_index"]
            out["warnings"] = [CHANCE_QUALITY_MACRO_WARNING]
    return out


def _patch_macroareas(macroareas: list[dict[str, Any]], *, feed_unavailable: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ma in macroareas:
        if not isinstance(ma, dict):
            continue
        key = str(ma.get("key") or "")
        patched = dict(ma)
        micros = ma.get("micros") if isinstance(ma.get("micros"), list) else []
        patched_micros: list[dict[str, Any]] = []
        for m in micros:
            if not isinstance(m, dict):
                patched_micros.append(m)
                continue
            pm = dict(m)
            if feed_unavailable and str(pm.get("key") or "") in XG_MICRO_KEYS:
                pm["status"] = "feed_unavailable"
                pm["source_path"] = FEED_UNAVAILABLE_SOURCE
                pm["raw_value"] = None
                pm["normalized_value"] = round(float(pm.get("normalized_value") or 1.0), 2)
                pm["fallback_used"] = True
                pm["contribution"] = "neutra"
                pm["warning"] = XG_MISSING_WARNING
            patched_micros.append(pm)
        patched["micros"] = patched_micros
        if key == "chance_quality" and feed_unavailable:
            if patched_micros and all(
                str(m.get("status") or "") == "feed_unavailable"
                for m in patched_micros
                if str(m.get("key") or "") in XG_MICRO_KEYS
            ):
                patched["status"] = "degraded_feed_unavailable"
                patched["coverage_pct"] = 0.0
                patched["macro_index"] = round(float(patched.get("macro_index") or 1.0), 4)
                patched["warnings"] = [CHANCE_QUALITY_MACRO_WARNING]
        out.append(patched)
    return out


def enrich_v21_raw_for_audit(
    raw: dict[str, Any] | None,
    db: Session | None = None,
    competition_id: int | None = None,
    fixture_id: int | None = None,
) -> dict[str, Any]:
    """Copia arricchita per trace/audit; non altera valori numerici di prediction."""
    if not isinstance(raw, dict):
        return {}
    out = copy.deepcopy(raw)
    feed_unavailable = _is_xg_feed_unavailable(out, db, competition_id)

    components = out.get("components") if isinstance(out.get("components"), dict) else {}
    patched_components: dict[str, Any] = {}
    for mk, comp in components.items():
        if isinstance(comp, dict):
            patched_components[mk] = _patch_macro_component(comp, macro_key=str(mk), feed_unavailable=feed_unavailable)
        else:
            patched_components[mk] = comp
    out["components"] = patched_components

    macroareas = out.get("macroareas") if isinstance(out.get("macroareas"), list) else []
    if macroareas:
        out["macroareas"] = _patch_macroareas(macroareas, feed_unavailable=feed_unavailable)

    _ = fixture_id  # riservato per anchor_breakdown futuro
    return out


def build_v21_coverage_summary_from_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    components = raw.get("components") if isinstance(raw.get("components"), dict) else {}
    predictive_used = 0
    micro_available = 0
    micro_fallback = 0
    micro_feed_unavailable = 0
    micro_not_tracked = 0
    micro_missing_real = 0
    total_micro = 0

    for mk in PREDICTIVE_MACRO_KEYS:
        comp = components.get(mk) if isinstance(components.get(mk), dict) else {}
        if comp:
            predictive_used += 1
        inputs = comp.get("inputs") if isinstance(comp.get("inputs"), dict) else {}
        for inp in inputs.values():
            if not isinstance(inp, dict):
                continue
            total_micro += 1
            st = str(inp.get("status") or "missing")
            norm = float(inp.get("normalized_value") or 1.0)
            if st in ("available", "available_derived", "partial"):
                micro_available += 1
            elif st == "feed_unavailable":
                micro_feed_unavailable += 1
            elif st == "not_tracked_yet":
                micro_not_tracked += 1
            elif st == "missing":
                micro_missing_real += 1
            elif st in ("fallback", "fallback_partial", "fallback_historical_profiles", "missing_dependency"):
                if abs(norm - 1.0) < 0.001:
                    micro_fallback += 1
                else:
                    micro_available += 1

    quality = components.get(QUALITY_MACRO_KEY) if isinstance(components.get(QUALITY_MACRO_KEY), dict) else None
    return {
        "predictive_macros_used": f"{predictive_used}/{len(PREDICTIVE_MACRO_KEYS)}",
        "micro_available": micro_available,
        "micro_fallback_neutral": micro_fallback,
        "micro_feed_unavailable": micro_feed_unavailable,
        "micro_not_tracked_yet": micro_not_tracked,
        "micro_missing_real": micro_missing_real,
        "micro_total": total_micro,
        "quality_macro_present": quality is not None,
        "quality_macro_note": "usata per confidence, non per SOT",
    }
