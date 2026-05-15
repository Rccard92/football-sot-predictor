"""
Ricostruzione esplicita dei 6 termini esterni della formula v0.4 da raw_json già persistito.
Non usa predicted_sot v0.4 nel calcolo: valori da componente offensiva, baseline_other_inputs
e (se necessario) calculation_breakdown v0.1 — mai placeholder silenziosi.
"""

from __future__ import annotations

from typing import Any

WEIGHT_OFFENSIVE = 0.30

# key, weight, label, formula, source_path primario, chiave v0.1 calculation_breakdown
V10_BASE_TERM_SPECS: list[tuple[str, float, str, str, str, str | None]] = [
    (
        "opp_avg_sot_conceded",
        0.25,
        "Tiri in porta concessi dall'avversario (stagione)",
        "value × 0.25 (stesso mix v0.4)",
        "debug.baseline_other_inputs.opp_avg_sot_conceded",
        "opponent_season_avg_sot_conceded",
    ),
    (
        "team_split_avg_sot_for",
        0.15,
        "SOT fatti in split casa/trasferta",
        "value × 0.15",
        "debug.baseline_other_inputs.team_split_avg_sot_for",
        "team_home_away_avg_sot_for",
    ),
    (
        "opp_split_avg_sot_conceded",
        0.10,
        "SOT concessi avversario in split",
        "value × 0.10",
        "debug.baseline_other_inputs.opp_split_avg_sot_conceded",
        "opponent_home_away_avg_sot_conceded",
    ),
    (
        "team_last5_avg_sot_for",
        0.10,
        "SOT fatti ultime 5",
        "value × 0.10",
        "debug.baseline_other_inputs.team_last5_avg_sot_for",
        "team_last5_avg_sot_for",
    ),
    (
        "opp_last5_avg_sot_conceded",
        0.10,
        "SOT concessi avversario ultime 5",
        "value × 0.10",
        "debug.baseline_other_inputs.opp_last5_avg_sot_conceded",
        "opponent_last5_avg_sot_conceded",
    ),
]

PLACEHOLDER_REASON = "Valore uguale al componente offensivo (probabile placeholder v0.4)"
MISSING_V04_REASON = "Valore non trovato nel raw_json v0.4 né in calculation_breakdown v0.1"
DUPLICATE_VALUES_WARNING = "Valori formula sospetti: più termini hanno lo stesso valore"


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


def _r4(x: float) -> float:
    return round(float(x), 4)


def _r2(x: float) -> float:
    return round(float(x), 2)


def alignment_status(delta: float) -> str:
    ad = abs(float(delta))
    if ad <= 0.03:
        return "aligned_with_v04"
    if ad <= 0.10:
        return "minor_rounding_difference"
    return "needs_review"


def _v01_breakdown(raw_v01: dict[str, Any] | None) -> dict[str, Any]:
    if not raw_v01 or not isinstance(raw_v01, dict):
        return {}
    bd = raw_v01.get("calculation_breakdown")
    return bd if isinstance(bd, dict) else {}


def _is_placeholder_value(val: float | None, offensive_val: float | None) -> bool:
    if val is None or offensive_val is None:
        return False
    return abs(float(val) - float(offensive_val)) < 1e-6


def _make_term(
    *,
    key: str,
    label: str,
    weight: float,
    value: float | None,
    formula: str,
    source_path: str,
    fallback_used: bool,
    fallback_reason: str | None,
    cap_applied: bool = False,
) -> dict[str, Any]:
    if value is not None and not fallback_used:
        contrib = _r4(float(value) * float(weight))
        status = "available"
    else:
        contrib = 0.0
        status = "fallback" if fallback_used else "missing"
    return {
        "key": key,
        "label": label,
        "value": _r2(float(value)) if value is not None else None,
        "weight": weight,
        "contribution": contrib,
        "formula": formula,
        "source": source_path,
        "source_path": source_path,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "status": status,
        "cap_applied": cap_applied,
        "application_role": "direct_formula_component",
        "parent_component": None,
    }


def _resolve_baseline_term_value(
    key: str,
    bo: dict[str, Any],
    bd_v01: dict[str, Any],
    v01_key: str | None,
    offensive_val: float | None,
) -> tuple[float | None, str, bool, str | None]:
    """Ritorna (value, source_path, fallback_used, fallback_reason)."""
    bo_val = _sf(bo.get(key)) if key in bo else None
    v01_val = _sf(bd_v01.get(v01_key)) if v01_key and v01_key in bd_v01 else None

    if bo_val is not None and not _is_placeholder_value(bo_val, offensive_val):
        return bo_val, f"debug.baseline_other_inputs.{key}", False, None

    if v01_val is not None:
        return v01_val, f"calculation_breakdown.{v01_key}", False, None

    if bo_val is not None and _is_placeholder_value(bo_val, offensive_val):
        if v01_val is not None:
            return v01_val, f"calculation_breakdown.{v01_key}", True, PLACEHOLDER_REASON
        return None, f"debug.baseline_other_inputs.{key}", True, PLACEHOLDER_REASON

    return None, f"debug.baseline_other_inputs.{key}", True, MISSING_V04_REASON


def detect_suspicious_term_values(terms: list[dict[str, Any]]) -> list[str]:
    """Warning se ≥4 termini base (escluso offensivo) condividono lo stesso value senza fallback."""
    base = [t for t in terms if t.get("key") != "offensive_production_component"]
    warnings: list[str] = []
    by_value: dict[float, list[dict[str, Any]]] = {}
    for t in base:
        v = t.get("value")
        if v is None:
            continue
        fv = round(float(v), 4)
        by_value.setdefault(fv, []).append(t)

    for val, group in by_value.items():
        if len(group) < 4:
            continue
        if all(bool(t.get("fallback_used")) for t in group):
            continue
        paths = {str(t.get("source_path") or "") for t in group}
        if len(paths) > 1:
            warnings.append(DUPLICATE_VALUES_WARNING)
            break
        if len(group) >= 4:
            off = next((t for t in terms if t.get("key") == "offensive_production_component"), None)
            off_v = _sf(off.get("value")) if off else None
            if off_v is not None and abs(float(val) - float(off_v)) < 1e-6:
                warnings.append(DUPLICATE_VALUES_WARNING)
                break
    return warnings


def assess_formula_quality(terms: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = detect_suspicious_term_values(terms)
    critical_fallback = sum(
        1
        for t in terms
        if t.get("key") != "offensive_production_component" and bool(t.get("fallback_used"))
    )
    if critical_fallback > 0:
        warnings.append(f"{critical_fallback} termini base con fallback o valore mancante")
    status = "ok"
    if warnings:
        status = "needs_review"
    if any(t.get("value") is None and t.get("key") != "expected_goals" for t in terms):
        status = "needs_review"
    return {
        "formula_quality_status": status,
        "formula_quality_warnings": warnings,
    }


def build_explicit_v04_terms_from_saved_raw(
    raw_v04: dict[str, Any],
    *,
    raw_v01: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], float, dict[str, Any]]:
    """
    Ritorna (terms, base_explicit_sot, quality_meta).
    base_explicit_sot = somma contributi dei 6 termini base (arrotondato 2 decimali).
    """
    comp = raw_v04.get("offensive_production_component")
    dbg = raw_v04.get("debug") if isinstance(raw_v04.get("debug"), dict) else {}
    bo = dbg.get("baseline_other_inputs") if isinstance(dbg.get("baseline_other_inputs"), dict) else None

    if not isinstance(comp, dict):
        raise ValueError("missing_offensive_production_component")
    if bo is None:
        raise ValueError("missing_baseline_other_inputs")

    off_val = _sf(comp.get("value"))
    if off_val is None:
        raise ValueError("missing_offensive_component_value")

    fb_list_off = comp.get("fallbacks_used") if isinstance(comp.get("fallbacks_used"), list) else []
    bd_v01 = _v01_breakdown(raw_v01)

    terms: list[dict[str, Any]] = []
    terms.append(
        _make_term(
            key="offensive_production_component",
            label="Produzione offensiva (componente v0.4)",
            weight=WEIGHT_OFFENSIVE,
            value=float(off_val),
            formula="valore componente offensiva (blend interno + cap) × 0.30",
            source_path="raw_json.offensive_production_component.value",
            fallback_used=bool(fb_list_off),
            fallback_reason="Fallback componente offensiva v0.4" if fb_list_off else None,
            cap_applied=bool(comp.get("cap_applied")),
        ),
    )

    for key, w, label, formula, source_path, v01_key in V10_BASE_TERM_SPECS:
        val, sp, fb, fb_reason = _resolve_baseline_term_value(
            key, bo, bd_v01, v01_key, off_val,
        )
        terms.append(
            _make_term(
                key=key,
                label=label,
                weight=w,
                value=val,
                formula=formula,
                source_path=sp,
                fallback_used=fb,
                fallback_reason=fb_reason,
            ),
        )

    quality_meta = assess_formula_quality(terms)
    total = sum(float(t["contribution"]) for t in terms)
    expected = _r2(total)
    return terms, float(expected), quality_meta


def build_formula_strings(terms: list[dict[str, Any]], expected: float) -> tuple[str, str]:
    sym_parts = []
    num_parts = []
    for t in terms:
        v = t.get("value")
        if v is not None:
            sym_parts.append(f"({_r2(float(v))} × {t['weight']})")
        else:
            sym_parts.append(f"(— × {t['weight']})")
        num_parts.append(f"({_r4(float(t['contribution']))})")
    symbolic = "expected_sot_v1 = " + " + ".join(sym_parts)
    numeric = (
        "expected_sot_v1 = "
        + " + ".join(num_parts)
        + f"\n= {_r4(sum(float(t['contribution']) for t in terms))}\n= {_r2(expected)}"
    )
    return symbolic, numeric


def build_xg_formula_term(xg_component: dict[str, Any]) -> dict[str, Any]:
    """7° termine: correzione additiva expected_goals (sempre presente)."""
    from app.services.predictions_v10.xg_adjustment_component import XG_SENSITIVITY

    applied = bool(xg_component.get("xg_adjustment_applied"))
    adj_sot = float(xg_component.get("xg_adjustment_sot") or 0.0)
    team_avg = _sf(xg_component.get("team_avg_xg_for"))
    fb = bool(xg_component.get("fallback_used")) or not applied
    src = str(xg_component.get("source") or "fixtures/statistics::expected_goals")
    return {
        "key": "expected_goals",
        "label": "xG / Expected goals",
        "type": "adjustment_component",
        "value": _r2(team_avg) if team_avg is not None else None,
        "weight": XG_SENSITIVITY,
        "contribution": _r4(adj_sot) if applied else 0.0,
        "formula": "base_explicit_sot * xg_adjustment_pct",
        "source": src,
        "source_path": "fixture_team_stats.expected_goals",
        "status": "available" if applied else "fallback",
        "fallback_used": fb,
        "fallback_reason": str(xg_component.get("fallback_reason") or "") or None,
        "cap_applied": bool(xg_component.get("cap_applied")),
        "application_role": "direct_formula_component",
        "parent_component": "xg_quality_component",
    }


def build_formula_payload_v10(
    base_terms: list[dict[str, Any]],
    *,
    base_explicit_sot: float,
    xg_component: dict[str, Any],
    final_sot: float,
) -> dict[str, Any]:
    xg_term = build_xg_formula_term(xg_component)
    all_terms = list(base_terms) + [xg_term]
    adj_sum = float(xg_term.get("contribution") or 0.0)
    base_sum = _r2(base_explicit_sot)

    base_sym = []
    base_num = []
    for t in base_terms:
        v = t.get("value")
        if v is not None:
            base_sym.append(f"({_r2(float(v))} × {t['weight']})")
        else:
            base_sym.append(f"(— × {t['weight']})")
        base_num.append(f"({_r4(float(t['contribution']))})")
    xg_sym = f"xG_adjustment({_r2(adj_sum)})"
    xg_num = f"{_r4(adj_sum)}"

    symbolic = "expected_sot_v1 = " + " + ".join(base_sym) + " + " + xg_sym
    numeric = (
        "expected_sot_v1 = "
        + " + ".join(base_num)
        + f" + {xg_num}\n= {_r4(float(base_explicit_sot) + adj_sum)}\n= {_r2(final_sot)}"
    )

    return {
        "type": "explicit_weighted_sum_plus_adjustments",
        "base_terms_count": 6,
        "adjustment_terms_count": 1,
        "terms_count": 7,
        "terms": all_terms,
        "base_sum": base_sum,
        "adjustment_sum": _r2(adj_sum),
        "final_sum": _r2(final_sot),
        "symbolic": symbolic,
        "numeric": numeric,
    }
