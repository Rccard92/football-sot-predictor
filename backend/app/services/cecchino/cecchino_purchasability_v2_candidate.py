"""Acquistabilità v2 — candidate decision_quality_v2.

Parallela a balanced_geometric_v1_1. Non modifica v1.1.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Any

from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
    PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
    PURCHASABILITY_V2_CONTRACT_VERSION,
    PURCHASABILITY_V2_FEATURE_VERSION,
    PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
    PURCHASABILITY_V2_NORM_PROFILE_VERSION,
    PURCHASABILITY_V2_REGISTRY_STATUS,
    PURCHASABILITY_V2_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_candidate import (
    CLASS_THRESHOLDS,
    map_score_to_class,
    round_purchasability_score_half_up,
)
from app.services.cecchino.cecchino_purchasability_fair_book import (
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
)
from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    get_or_build_normalization_profile,
    normalize_component_value,
)
from app.services.cecchino.cecchino_purchasability_v2_opposition import (
    SUPPORTED_V2_MARKETS,
    competitors_for_market,
    decision_group_for_market,
    is_v2_supported_market,
    probability_competitors_for_market,
    probability_profile_scope_for_market,
    profile_scope_for_market,
    resolve_opposite_selection,
)

PHASE_1_FORMULA_VERSION = "purchasability_v2_phase_1_absolute_value_v1"
PHASE_2_FORMULA_VERSION = "purchasability_v2_phase_2_decision_quality_v1"
FINAL_FORMULA_VERSION = "purchasability_v2_final_geometric_v1"

PHASE_1_CONFIGURED_WEIGHTS = MappingProxyType(
    {
        "rating": 0.30,
        "edge_pct": 0.40,
        "vantaggio_prob": 0.30,
    }
)

PHASE_2_CONFIGURED_WEIGHTS = MappingProxyType(
    {
        "dominance_rating": 0.25,
        "dominance_edge_pct": 0.25,
        "dominance_probability_pp": 0.20,
        "shift_book_cecchino_pp": 0.15,
        "opposite_contrast_pp": 0.15,
    }
)

DOMINANCE_COMPONENTS = (
    "dominance_rating",
    "dominance_edge_pct",
    "dominance_probability_pp",
)
SHIFT_OR_CONTRAST = ("shift_book_cecchino_pp", "opposite_contrast_pp")

READING_BY_CLASS: dict[str, str] = {
    "Molto Bassa": (
        "L'opportunità decisionale risulta scarsamente sostenuta da valore, "
        "dominanza sui concorrenti e contrasto con il mercato opposto."
    ),
    "Bassa": (
        "L'opportunità decisionale presenta un supporto limitato rispetto "
        "ai concorrenti e al Book."
    ),
    "Media": (
        "L'opportunità decisionale è sostenuta in modo intermedio da valore "
        "e qualità del contesto competitivo."
    ),
    "Alta": (
        "L'opportunità decisionale è supportata da valore positivo e "
        "superiorità coerente rispetto ai concorrenti."
    ),
    "Molto Alta": (
        "L'opportunità decisionale è fortemente supportata da valore, "
        "dominanza e contrasto con il mercato opposto."
    ),
}

READING_POSITIVE_VALUE_GATE_FAILED = (
    "Non acquistabile: il mercato non presenta contemporaneamente "
    "valore economico e vantaggio probabilistico positivi rispetto al Book."
)

PURCHASABILITY_DECISION_V2_REGISTRY = MappingProxyType(
    {
        PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION: MappingProxyType(
            {
                "name": PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
                "status": PURCHASABILITY_V2_REGISTRY_STATUS,
                "contract_version": PURCHASABILITY_V2_CONTRACT_VERSION,
                "feature_version": PURCHASABILITY_V2_FEATURE_VERSION,
                "snapshot_version": PURCHASABILITY_V2_SNAPSHOT_VERSION,
                "phase_1_formula": PHASE_1_FORMULA_VERSION,
                "phase_2_formula": PHASE_2_FORMULA_VERSION,
                "final_formula": FINAL_FORMULA_VERSION,
                "class_thresholds": CLASS_THRESHOLDS,
                "configured_weights_phase_1": PHASE_1_CONFIGURED_WEIGHTS,
                "configured_weights_phase_2": PHASE_2_CONFIGURED_WEIGHTS,
                "weight_policy": MappingProxyType(
                    {
                        "kind": "initial_research_weights",
                        "empirically_promoted": False,
                        "label": "not_empirically_promoted",
                    }
                ),
                "rounding_policy": "round_half_up",
                "uses_score_acquisto": False,
                "uses_historical_reliability": False,
                "normalization_profile_version": PURCHASABILITY_V2_NORM_PROFILE_VERSION,
                "ui_integration": True,
                "persistence": "compact_pre_match_snapshot_v2",
                "validation_promotion": False,
            }
        ),
    }
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _round2(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _panel_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        mk = row.get("market_key") or row.get("segno")
        if isinstance(mk, str) and mk:
            out[mk] = row
    return out


def _model_prob_map(
    panel_rows: list[dict[str, Any]],
) -> dict[str, float | None]:
    raw = build_model_context_probability_map(panel_rows)
    out: dict[str, float | None] = {}
    for mk, meta in raw.items():
        if isinstance(meta, dict):
            out[mk] = _safe_float(meta.get("model_context_probability"))
        else:
            out[mk] = _safe_float(meta)
    return out


def _fair_prob_map(
    panel_rows: list[dict[str, Any]],
    *,
    today_fixture_id: Any = None,
    snapshot_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    return resolve_fair_book_for_panel_rows(
        panel_rows,
        today_fixture_id=today_fixture_id,
        snapshot_at=snapshot_at,
    )


def _fair_prob_value(fair_info: dict[str, Any] | None) -> float | None:
    if not isinstance(fair_info, dict):
        return None
    verified = fair_info.get("fair_book_probability_verified")
    val = _safe_float(fair_info.get("fair_book_probability"))
    if verified is False:
        return None
    return val


def _renormalize_weights(
    configured: dict[str, float],
    available: list[str],
) -> dict[str, float]:
    total = sum(float(configured[k]) for k in available if k in configured)
    if total <= 0:
        return {}
    return {k: float(configured[k]) / total for k in available if k in configured}


def _calculate_phase_1(
    row: dict[str, Any],
    *,
    scope: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    configured = dict(PHASE_1_CONFIGURED_WEIGHTS)
    rating = _safe_float(row.get("rating"))
    edge = _safe_float(row.get("edge_pct"))
    vant = _safe_float(row.get("vantaggio_prob"))
    vant_pp = None if vant is None else vant * 100.0

    components: dict[str, Any] = {}
    available: list[str] = []
    missing: list[str] = []

    # Rating: no historical normalization (already 0–100)
    if rating is not None:
        available.append("rating")
        clamp_rating = max(0.0, min(100.0, rating))
        components["rating"] = {
            "raw_value": rating,
            "normalized_value": clamp_rating,
            "configured_weight": configured["rating"],
            "status": "available",
            "normalization": {
                "raw_value": rating,
                "normalized_value": clamp_rating,
                "positive_cap": None,
                "negative_cap": None,
                "profile_scope": scope,
                "profile_version": profile.get("version"),
                "cap_source": "rating_passthrough",
                "clipping_applied": rating < 0 or rating > 100,
            },
        }
    else:
        missing.append("rating")
        components["rating"] = {"status": "missing", "raw_value": None}

    edge_norm = normalize_component_value(
        edge, component="edge_pct", scope=scope, profile=profile
    )
    if edge is not None:
        available.append("edge_pct")
        components["edge_pct"] = {
            "raw_value": edge,
            "normalized_value": edge_norm.get("normalized_value"),
            "configured_weight": configured["edge_pct"],
            "status": "available",
            "normalization": edge_norm,
        }
    else:
        missing.append("edge_pct")
        components["edge_pct"] = {
            "status": "missing",
            "raw_value": None,
            "normalization": edge_norm,
        }

    vant_norm = normalize_component_value(
        vant_pp, component="vantaggio_prob_pp", scope=scope, profile=profile
    )
    if vant is not None:
        available.append("vantaggio_prob")
        components["vantaggio_prob"] = {
            "raw_value": vant,
            "raw_value_pp": vant_pp,
            "normalized_value": vant_norm.get("normalized_value"),
            "configured_weight": configured["vantaggio_prob"],
            "status": "available",
            "normalization": vant_norm,
        }
    else:
        missing.append("vantaggio_prob")
        components["vantaggio_prob"] = {
            "status": "missing",
            "raw_value": None,
            "normalization": vant_norm,
        }

    has_edge_or_vant = ("edge_pct" in available) or ("vantaggio_prob" in available)
    minimum_met = len(available) >= 2 and has_edge_or_vant
    reason_codes: list[str] = []

    if not minimum_met:
        return {
            "score": None,
            "status": "unavailable",
            "configured_weights": configured,
            "applied_weights": {},
            "coverage_ratio": len(available) / 3.0,
            "available_components": available,
            "missing_components": missing,
            "minimum_coverage_met": False,
            "components": components,
            "reason_codes": ["phase_1_minimum_coverage_not_met"],
            "formula_version": PHASE_1_FORMULA_VERSION,
            "score_acquisto_used": False,
            "historical_reliability_used": False,
        }

    applied = _renormalize_weights(configured, available)
    score = 0.0
    for key in available:
        norm_val = components[key].get("normalized_value")
        w = applied.get(key, 0.0)
        contrib = float(norm_val) * w if norm_val is not None else 0.0
        components[key]["applied_weight"] = w
        components[key]["contribution"] = _round2(contrib)
        score += contrib

    status = "available" if len(available) == 3 else "partial"
    if status == "partial":
        reason_codes.append("phase_1_partial_coverage")

    return {
        "score": _round2(score),
        "status": status,
        "configured_weights": configured,
        "applied_weights": applied,
        "coverage_ratio": len(available) / 3.0,
        "available_components": available,
        "missing_components": missing,
        "minimum_coverage_met": True,
        "components": components,
        "reason_codes": reason_codes,
        "formula_version": PHASE_1_FORMULA_VERSION,
        "score_acquisto_used": False,
        "historical_reliability_used": False,
    }


def _evaluate_positive_value_gate(
    row: dict[str, Any],
) -> dict[str, Any]:
    edge = _safe_float(row.get("edge_pct"))
    vant = _safe_float(row.get("vantaggio_prob"))
    reason_codes: list[str] = []
    edge_available = edge is not None
    vant_available = vant is not None
    edge_positive = edge > 0 if edge is not None else None
    vant_positive = vant > 0 if vant is not None else None

    failed = False
    if edge_available and edge is not None and edge <= 0:
        failed = True
        reason_codes.append("no_positive_edge")
    if vant_available and vant is not None and vant <= 0:
        failed = True
        reason_codes.append("no_positive_probability_advantage")
    if failed:
        reason_codes.append("positive_value_gate_failed")
        return {
            "status": "failed",
            "reason_codes": reason_codes,
            "edge_available": edge_available,
            "edge_positive": edge_positive,
            "vantaggio_available": vant_available,
            "vantaggio_positive": vant_positive,
            "reading": READING_POSITIVE_VALUE_GATE_FAILED,
        }
    if not edge_available and not vant_available:
        return {
            "status": "unavailable",
            "reason_codes": ["positive_value_gate_inputs_missing"],
            "edge_available": False,
            "edge_positive": None,
            "vantaggio_available": False,
            "vantaggio_positive": None,
            "reading": None,
        }
    return {
        "status": "passed",
        "reason_codes": [],
        "edge_available": edge_available,
        "edge_positive": edge_positive if edge_available else None,
        "vantaggio_available": vant_available,
        "vantaggio_positive": vant_positive if vant_available else None,
        "reading": None,
    }


def _best_competitor(
    by_mk: dict[str, dict[str, Any]],
    competitors: list[str],
    field: str,
    *,
    value_map: dict[str, float | None] | None = None,
) -> tuple[str | None, float | None]:
    best_mk: str | None = None
    best_val: float | None = None
    for c in competitors:
        if value_map is not None:
            val = _safe_float(value_map.get(c))
        else:
            val = _safe_float((by_mk.get(c) or {}).get(field))
        if val is None:
            continue
        if best_val is None or val > best_val:
            best_val = val
            best_mk = c
    return best_mk, best_val


def _calculate_phase_2(
    market_key: str,
    row: dict[str, Any],
    by_mk: dict[str, dict[str, Any]],
    *,
    scope: str,
    prob_scope: str | None,
    profile: dict[str, Any],
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None],
) -> dict[str, Any]:
    configured = dict(PHASE_2_CONFIGURED_WEIGHTS)
    comps = competitors_for_market(market_key)
    pcomps = probability_competitors_for_market(market_key)

    selected_rating = _safe_float(row.get("rating"))
    selected_edge = _safe_float(row.get("edge_pct"))
    selected_model = _safe_float(model_probs.get(market_key))
    fair_info = fair_by.get(market_key)
    selected_fair = _fair_prob_value(fair_info)

    fair_probs_only = {
        mk: _fair_prob_value(info) for mk, info in fair_by.items()
    }
    opp = resolve_opposite_selection(
        market_key, fair_book_by_market=fair_probs_only
    )

    best_r_mk, best_r = _best_competitor(by_mk, comps, "rating")
    best_e_mk, best_e = _best_competitor(by_mk, comps, "edge_pct")
    best_p_mk, best_p = _best_competitor(
        by_mk, pcomps, "prob_cecchino", value_map=model_probs
    )

    raw_dom_rating = (
        selected_rating - best_r
        if selected_rating is not None and best_r is not None
        else None
    )
    raw_dom_edge = (
        selected_edge - best_e
        if selected_edge is not None and best_e is not None
        else None
    )
    raw_dom_prob_pp = (
        (selected_model - best_p) * 100.0
        if selected_model is not None and best_p is not None
        else None
    )
    raw_shift_pp = (
        (selected_model - selected_fair) * 100.0
        if selected_model is not None and selected_fair is not None
        else None
    )
    opp_fair = _safe_float(opp.get("opposite_fair_book_probability"))
    raw_contrast_pp = (
        (selected_model - opp_fair) * 100.0
        if selected_model is not None and opp_fair is not None
        else None
    )

    raw_map = {
        "dominance_rating": raw_dom_rating,
        "dominance_edge_pct": raw_dom_edge,
        "dominance_probability_pp": raw_dom_prob_pp,
        "shift_book_cecchino_pp": raw_shift_pp,
        "opposite_contrast_pp": raw_contrast_pp,
    }
    scope_map = {
        "dominance_rating": scope,
        "dominance_edge_pct": scope,
        "dominance_probability_pp": prob_scope or scope,
        "shift_book_cecchino_pp": scope,
        "opposite_contrast_pp": scope,
    }
    best_mk_map = {
        "dominance_rating": best_r_mk,
        "dominance_edge_pct": best_e_mk,
        "dominance_probability_pp": best_p_mk,
        "shift_book_cecchino_pp": None,
        "opposite_contrast_pp": opp.get("opposite_selection"),
    }
    selected_val_map = {
        "dominance_rating": selected_rating,
        "dominance_edge_pct": selected_edge,
        "dominance_probability_pp": (
            None if selected_model is None else selected_model * 100.0
        ),
        "shift_book_cecchino_pp": (
            None if selected_model is None else selected_model * 100.0
        ),
        "opposite_contrast_pp": (
            None if selected_model is None else selected_model * 100.0
        ),
    }
    best_val_map = {
        "dominance_rating": best_r,
        "dominance_edge_pct": best_e,
        "dominance_probability_pp": None if best_p is None else best_p * 100.0,
        "shift_book_cecchino_pp": (
            None if selected_fair is None else selected_fair * 100.0
        ),
        "opposite_contrast_pp": None if opp_fair is None else opp_fair * 100.0,
    }

    components: dict[str, Any] = {}
    available: list[str] = []
    missing: list[str] = []
    reason_codes: list[str] = []

    for key, raw in raw_map.items():
        sc = scope_map[key]
        norm = normalize_component_value(
            raw, component=key, scope=sc, profile=profile
        )
        if raw is None:
            missing.append(key)
            components[key] = {
                "status": "missing",
                "raw_value": None,
                "normalized_value": None,
                "configured_weight": configured[key],
                "normalization": norm,
                "best_competitor_market": best_mk_map[key],
                "selected_value": selected_val_map[key],
                "best_competitor_value": best_val_map[key],
            }
        else:
            available.append(key)
            components[key] = {
                "status": "available",
                "raw_value": raw,
                "normalized_value": norm.get("normalized_value"),
                "configured_weight": configured[key],
                "normalization": norm,
                "best_competitor_market": best_mk_map[key],
                "selected_value": selected_val_map[key],
                "best_competitor_value": best_val_map[key],
            }

    if selected_fair is None:
        reason_codes.append("fair_book_unverified_or_missing")
    if selected_model is None:
        reason_codes.append("model_context_probability_missing")

    has_dominance = any(k in available for k in DOMINANCE_COMPONENTS)
    has_shift_or_contrast = any(k in available for k in SHIFT_OR_CONTRAST)
    minimum_met = len(available) >= 3 and has_dominance and has_shift_or_contrast

    competitor_trace = {
        "decision_group": scope,
        "probability_subgroup": prob_scope,
        "competitors_considered": comps,
        "probability_competitors_considered": pcomps,
        "best_competitor_rating_market": best_r_mk,
        "best_competitor_rating": best_r,
        "best_competitor_edge_market": best_e_mk,
        "best_competitor_edge_pct": best_e,
        "best_competitor_probability_market": best_p_mk,
        "best_competitor_probability": best_p,
        "opposite_selection": opp.get("opposite_selection"),
        "opposite_fair_book_probability": opp_fair,
        "draw_opposite_trace": opp.get("draw_opposite_trace"),
        "selected_fair_book_probability": selected_fair,
        "selected_model_context_probability": selected_model,
    }

    if not minimum_met:
        return {
            "score": None,
            "status": "unavailable",
            "configured_weights": configured,
            "applied_weights": {},
            "coverage_ratio": len(available) / 5.0,
            "available_components": available,
            "missing_components": missing,
            "minimum_coverage_met": False,
            "weight_policy": {
                "kind": "initial_research_weights",
                "empirically_promoted": False,
                "label": "not_empirically_promoted",
            },
            "components": components,
            "competitor_trace": competitor_trace,
            "reason_codes": reason_codes + ["phase_2_minimum_coverage_not_met"],
            "formula_version": PHASE_2_FORMULA_VERSION,
        }

    applied = _renormalize_weights(configured, available)
    score = 0.0
    for key in available:
        norm_val = components[key].get("normalized_value")
        w = applied.get(key, 0.0)
        contrib = float(norm_val) * w if norm_val is not None else 0.0
        components[key]["applied_weight"] = w
        components[key]["contribution"] = _round2(contrib)
        score += contrib

    status = "available" if len(available) == 5 else "partial"
    if status == "partial":
        reason_codes.append("phase_2_partial_coverage")

    return {
        "score": _round2(score),
        "status": status,
        "configured_weights": configured,
        "applied_weights": applied,
        "coverage_ratio": len(available) / 5.0,
        "available_components": available,
        "missing_components": missing,
        "minimum_coverage_met": True,
        "weight_policy": {
            "kind": "initial_research_weights",
            "empirically_promoted": False,
            "label": "not_empirically_promoted",
        },
        "components": components,
        "competitor_trace": competitor_trace,
        "reason_codes": reason_codes,
        "formula_version": PHASE_2_FORMULA_VERSION,
    }


def calculate_purchasability_v2_item(
    market_key: str,
    row: dict[str, Any],
    by_mk: dict[str, dict[str, Any]],
    *,
    profile: dict[str, Any],
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None],
) -> dict[str, Any]:
    base_meta = {
        "candidate_version": PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
        "candidate_name": PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
        "contract_version": PURCHASABILITY_V2_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V2_FEATURE_VERSION,
        "market_key": market_key,
        "selection": market_key,
        "normalization_profile": {
            "version": profile.get("version"),
            "hash": profile.get("hash"),
            "cutoff": profile.get("cutoff"),
            "summary": profile.get("summary"),
        },
    }

    if not is_v2_supported_market(market_key):
        return make_json_safe(
            {
                **base_meta,
                "status": "unavailable",
                "calculation_quality": None,
                "score": None,
                "raw_score": None,
                "raw_pre_gate_score": None,
                "class": None,
                "reading": None,
                "phase_1_value": {},
                "phase_2_quality": {},
                "positive_value_gate": {"status": "unavailable", "reason_codes": []},
                "reason_codes": ["purchasability_v2_market_unsupported"],
                "data_quality": {"market_supported": False},
            }
        )

    scope = profile_scope_for_market(market_key) or "OUTCOMES"
    prob_scope = probability_profile_scope_for_market(market_key)

    phase_1 = _calculate_phase_1(row, scope=scope, profile=profile)
    phase_2 = _calculate_phase_2(
        market_key,
        row,
        by_mk,
        scope=scope,
        prob_scope=prob_scope,
        profile=profile,
        fair_by=fair_by,
        model_probs=model_probs,
    )
    gate = _evaluate_positive_value_gate(row)

    reason_codes: list[str] = []
    reason_codes.extend(phase_1.get("reason_codes") or [])
    reason_codes.extend(phase_2.get("reason_codes") or [])
    reason_codes.extend(gate.get("reason_codes") or [])

    p1 = phase_1.get("score")
    p2 = phase_2.get("score")
    if p1 is None or p2 is None:
        return make_json_safe(
            {
                **base_meta,
                "status": "unavailable",
                "calculation_quality": None,
                "score": None,
                "raw_score": None,
                "raw_pre_gate_score": None,
                "class": None,
                "reading": None,
                "phase_1_value": phase_1,
                "phase_2_quality": phase_2,
                "positive_value_gate": gate,
                "reason_codes": list(dict.fromkeys(reason_codes)),
                "data_quality": {
                    "market_supported": True,
                    "decision_group": decision_group_for_market(market_key),
                },
            }
        )

    raw_pre_gate = math.sqrt(float(p1) * float(p2))
    if gate.get("status") == "failed":
        raw_final = 0.0
    else:
        raw_final = raw_pre_gate

    score = round_purchasability_score_half_up(raw_final)
    klass = map_score_to_class(score)
    if gate.get("status") == "failed":
        reading = READING_POSITIVE_VALUE_GATE_FAILED
        klass = "Molto Bassa"
    else:
        reading = READING_BY_CLASS.get(klass or "", None)

    calc_quality = "full"
    status = "available"
    if phase_1.get("status") == "partial" or phase_2.get("status") == "partial":
        calc_quality = "partial"
        status = "partial"

    return make_json_safe(
        {
            **base_meta,
            "status": status,
            "calculation_quality": calc_quality,
            "score": score,
            "raw_score": _round2(raw_final),
            "raw_pre_gate_score": _round2(raw_pre_gate),
            "class": klass,
            "reading": reading,
            "phase_1_value": phase_1,
            "phase_2_quality": phase_2,
            "positive_value_gate": gate,
            "reason_codes": list(dict.fromkeys(reason_codes)),
            "data_quality": {
                "market_supported": True,
                "decision_group": decision_group_for_market(market_key),
                "probability_subgroup": prob_scope,
                "final_formula_version": FINAL_FORMULA_VERSION,
                "rounding": "Decimal_ROUND_HALF_UP",
            },
        }
    )


def calculate_purchasability_v2_batch(
    *,
    kpi_panel: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
    fixture_meta: dict[str, Any] | None = None,
    db: Any | None = None,
) -> dict[str, Any]:
    meta = fixture_meta or {}
    norm_profile = get_or_build_normalization_profile(db, profile=profile)
    rows = _panel_rows(kpi_panel)
    by_mk = _index_rows(rows)
    fair_by = _fair_prob_map(
        rows,
        today_fixture_id=meta.get("today_fixture_id"),
        snapshot_at=(
            str(meta.get("snapshot_at")) if meta.get("snapshot_at") else None
        ),
    )
    model_probs = _model_prob_map(rows)

    items: list[dict[str, Any]] = []
    # Calcola per tutti i mercati supportati presenti nel panel + eventuali mancanti supportati
    markets = sorted(set(by_mk.keys()) | set(SUPPORTED_V2_MARKETS))
    # Preferisci solo mercati presenti nel panel o supportati nel panel
    panel_markets = [mk for mk in by_mk.keys() if is_v2_supported_market(mk)]
    # Include unsupported present in panel as unavailable
    extra_unsupported = [
        mk for mk in by_mk.keys() if not is_v2_supported_market(mk)
    ]
    ordered = list(dict.fromkeys(panel_markets + extra_unsupported))

    for mk in ordered:
        row = by_mk.get(mk) or {}
        items.append(
            calculate_purchasability_v2_item(
                mk,
                row,
                by_mk,
                profile=norm_profile,
                fair_by=fair_by,
                model_probs=model_probs,
            )
        )

    available_n = sum(1 for it in items if it.get("status") in ("available", "partial"))
    unavailable_n = sum(1 for it in items if it.get("status") == "unavailable")
    if available_n == 0:
        batch_status = "unavailable"
    elif unavailable_n > 0 or any(it.get("status") == "partial" for it in items):
        batch_status = "partial"
    else:
        batch_status = "ok"

    payload = {
        "candidate_version": PURCHASABILITY_DECISION_V2_CANDIDATE_VERSION,
        "candidate_name": PURCHASABILITY_DECISION_V2_CANDIDATE_NAME,
        "contract_version": PURCHASABILITY_V2_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V2_FEATURE_VERSION,
        "status": batch_status,
        "items": items,
        "summary": {
            "markets_total": len(items),
            "available": available_n,
            "unavailable": unavailable_n,
            "partial": sum(1 for it in items if it.get("status") == "partial"),
        },
        "normalization_profile_version": norm_profile.get("version"),
        "normalization_profile_hash": norm_profile.get("hash"),
        "normalization_profile_cutoff": norm_profile.get("cutoff")
        or PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
        "normalization_profile_summary": norm_profile.get("summary"),
        "registry_status": PURCHASABILITY_V2_REGISTRY_STATUS,
    }
    return make_json_safe(payload)


def canonical_v2_candidate_sha256(batch: dict[str, Any]) -> str:
    raw = json.dumps(batch, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
