"""
Ricostruzione esplicita dei 6 termini esterni della formula v0.4 da raw_json già persistito.
Non usa predicted_sot v0.4 nel calcolo: solo valori in offensive_production_component e debug.baseline_other_inputs.
"""

from __future__ import annotations

from typing import Any

# Pesi esterni identici a SotPredictionV04OffensiveCoreSotService._expected_sot_v04_from_baseline
WEIGHT_OFFENSIVE = 0.30
WEIGHT_BASELINE: list[tuple[str, float, str, str, str]] = [
    (
        "opp_avg_sot_conceded",
        0.25,
        "Tiri in porta concessi dall'avversario (stagione)",
        "value × 0.25 (stesso mix v0.4)",
        "team_sot_predictions v0.1 breakdown / debug.baseline_other_inputs",
    ),
    (
        "team_split_avg_sot_for",
        0.15,
        "SOT fatti in split casa/trasferta",
        "value × 0.15",
        "team_sot_predictions v0.1 breakdown / debug.baseline_other_inputs",
    ),
    (
        "opp_split_avg_sot_conceded",
        0.10,
        "SOT concessi avversario in split",
        "value × 0.10",
        "team_sot_predictions v0.1 breakdown / debug.baseline_other_inputs",
    ),
    (
        "team_last5_avg_sot_for",
        0.10,
        "SOT fatti ultime 5",
        "value × 0.10",
        "team_sot_predictions v0.1 breakdown / debug.baseline_other_inputs",
    ),
    (
        "opp_last5_avg_sot_conceded",
        0.10,
        "SOT concessi avversario ultime 5",
        "value × 0.10",
        "team_sot_predictions v0.1 breakdown / debug.baseline_other_inputs",
    ),
]


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


def build_explicit_v04_terms_from_saved_raw(raw_v04: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    """
    Ritorna (terms, expected_sot_v1) con expected_sot_v1 = arrotondamento a 2 decimali della somma contributi.
    Solleva ValueError se raw incompleto.
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
    fb_off = bool(fb_list_off)
    cap_off = bool(comp.get("cap_applied"))

    terms: list[dict[str, Any]] = []

    c_off = _r4(float(off_val) * WEIGHT_OFFENSIVE)
    terms.append(
        {
            "key": "offensive_production_component",
            "label": "Produzione offensiva (componente v0.4)",
            "value": _r2(float(off_val)),
            "weight": WEIGHT_OFFENSIVE,
            "contribution": c_off,
            "formula": "valore componente offensiva (blend interno + cap) × 0.30",
            "source": "raw_json.offensive_production_component (stessa logica persistita v0.4)",
            "fallback_used": fb_off,
            "cap_applied": cap_off,
            "application_role": "direct_formula_component",
            "parent_component": None,
        },
    )

    for key, w, label, formula, source in WEIGHT_BASELINE:
        if key not in bo:
            raise ValueError(f"missing_baseline_key:{key}")
        val = _sf(bo.get(key))
        if val is None:
            raise ValueError(f"missing_baseline_value:{key}")
        c = _r4(float(val) * float(w))
        terms.append(
            {
                "key": key,
                "label": label,
                "value": _r2(float(val)),
                "weight": w,
                "contribution": c,
                "formula": formula,
                "source": source,
                "fallback_used": False,
                "cap_applied": False,
                "application_role": "direct_formula_component",
                "parent_component": None,
            },
        )

    total = sum(float(t["contribution"]) for t in terms)
    expected = _r2(total)
    return terms, float(expected)


def build_formula_strings(terms: list[dict[str, Any]], expected: float) -> tuple[str, str]:
    sym_parts = [f"({_r2(float(t['value']))} × {t['weight']})" for t in terms]
    num_parts = [f"({_r4(float(t['contribution']))})" for t in terms]
    symbolic = "expected_sot_v1 = " + " + ".join(sym_parts)
    numeric = "expected_sot_v1 = " + " + ".join(num_parts) + f"\n= {_r4(sum(float(t['contribution']) for t in terms))}\n= {_r2(expected)}"
    return symbolic, numeric


def build_xg_formula_term(xg_component: dict[str, Any]) -> dict[str, Any]:
    """7° termine: correzione additiva expected_goals."""
    from app.services.predictions_v10.xg_adjustment_component import XG_SENSITIVITY

    applied = bool(xg_component.get("xg_adjustment_applied"))
    adj_sot = float(xg_component.get("xg_adjustment_sot") or 0.0)
    team_avg = _sf(xg_component.get("team_avg_xg_for"))
    return {
        "key": "expected_goals",
        "label": "xG / Expected goals",
        "type": "adjustment_component",
        "value": _r2(team_avg) if team_avg is not None else None,
        "weight": XG_SENSITIVITY,
        "contribution": _r4(adj_sot) if applied else 0.0,
        "formula": "base_explicit_sot * xg_adjustment_pct",
        "source": str(xg_component.get("source") or "fixtures/statistics::expected_goals"),
        "status": "available" if applied else "fallback",
        "fallback_used": bool(xg_component.get("fallback_used")),
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

    base_sym = [f"({_r2(float(t['value']))} × {t['weight']})" for t in base_terms]
    base_num = [f"({_r4(float(t['contribution']))})" for t in base_terms]
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
        "terms": all_terms,
        "base_sum": base_sum,
        "adjustment_sum": _r2(adj_sum),
        "final_sum": _r2(final_sot),
        "symbolic": symbolic,
        "numeric": numeric,
    }
