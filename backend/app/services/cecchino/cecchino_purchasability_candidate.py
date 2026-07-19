"""Acquistabilità V1 Preview — candidato frozen Fase 3/5.

Versione: cecchino_purchasability_v1_preview_candidate_1
Nome: balanced_geometric_v1

Calcola score Phase1/Phase2 + finale geometrico sulle feature Fase 2.
Non importa Affidabilità storica. Non usa Rating/Score come peso.
Read-only, deterministico, JSON-safe. Nessuna persistenza.
"""

from __future__ import annotations

import json
import math
import statistics
from types import MappingProxyType
from typing import Any

from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_features import (
    build_purchasability_features_for_fixture,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

PURCHASABILITY_CANDIDATE_VERSION = "cecchino_purchasability_v1_preview_candidate_1"
PURCHASABILITY_CANDIDATE_NAME = "balanced_geometric_v1"

PHASE_1_FORMULA_VERSION = "purchasability_phase_1_value_v1"
PHASE_2_FORMULA_VERSION = "purchasability_phase_2_quality_v1"
FINAL_FORMULA_VERSION = "purchasability_final_geometric_v1"

CLASS_THRESHOLDS = (20, 40, 60, 80)

CONFIGURED_PHASE_2_WEIGHTS: dict[str, float] = {
    "model_opposition_support": 0.40,
    "book_opposition_resistance": 0.30,
    "opposite_favourite_intensity": 0.20,
    "favourite_alignment": 0.10,
}

REQUIRED_PHASE_2_COMPONENTS = (
    "model_opposition_support",
    "book_opposition_resistance",
)

OPTIONAL_PHASE_2_COMPONENTS = (
    "opposite_favourite_intensity",
    "favourite_alignment",
)

SUPPORTED_CANDIDATE_MARKETS = frozenset(
    {
        SEL_HOME,
        SEL_DRAW,
        SEL_AWAY,
        SEL_ONE_X,
        SEL_X_TWO,
        SEL_ONE_TWO,
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_PT_1_5,
        SEL_UNDER_PT_1_5,
    }
)

PURCHASABILITY_CANDIDATE_REGISTRY = MappingProxyType(
    {
        PURCHASABILITY_CANDIDATE_VERSION: MappingProxyType(
            {
                "name": PURCHASABILITY_CANDIDATE_NAME,
                "status": "frozen_preview",
                "phase_1_formula": PHASE_1_FORMULA_VERSION,
                "phase_2_formula": PHASE_2_FORMULA_VERSION,
                "final_formula": FINAL_FORMULA_VERSION,
                "class_thresholds": list(CLASS_THRESHOLDS),
                "uses_rating": False,
                "uses_historical_reliability": False,
                "uses_future_context_hooks": False,
                "configured_weights": dict(CONFIGURED_PHASE_2_WEIGHTS),
            }
        )
    }
)

PHASE_1_ACTIVE_INPUTS = ("prob_cecchino", "edge_pct")
PHASE_1_DIAGNOSTIC_INPUTS = (
    "vantaggio_prob",
    "score_acquisto",
    "rating",
    "rating_label",
)

READING_BY_CLASS: dict[str, str] = {
    "Molto Bassa": (
        "Il valore individuato è scarsamente sostenuto dalla struttura "
        "statistica e probabilistica dei mercati opposti."
    ),
    "Bassa": (
        "Il valore individuato presenta un supporto limitato nel contesto "
        "statistico e probabilistico della partita."
    ),
    "Media": (
        "Il valore individuato è sostenuto da una struttura statistica "
        "e probabilistica intermedia."
    ),
    "Alta": (
        "Il valore individuato è supportato da una struttura statistica "
        "e probabilistica coerente."
    ),
    "Molto Alta": (
        "Il valore individuato è supportato da una struttura statistica "
        "e probabilistica molto coerente."
    ),
}

CLASS_ORDER = ("Molto Bassa", "Bassa", "Media", "Alta", "Molto Alta")


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _round2(value: float) -> float:
    return round(value, 2)


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


def map_score_to_class(score: int | float | None) -> str | None:
    if score is None:
        return None
    s = float(score)
    if s < CLASS_THRESHOLDS[0]:
        return "Molto Bassa"
    if s < CLASS_THRESHOLDS[1]:
        return "Bassa"
    if s < CLASS_THRESHOLDS[2]:
        return "Media"
    if s < CLASS_THRESHOLDS[3]:
        return "Alta"
    return "Molto Alta"


def compare_purchasability_combiners(
    *,
    phase_1_score: float,
    phase_2_score: float,
) -> dict[str, Any]:
    p1 = float(phase_1_score)
    p2 = float(phase_2_score)
    geometric = math.sqrt(p1 * p2)
    arithmetic = 0.5 * p1 + 0.5 * p2
    if p1 + p2 == 0:
        harmonic = 0.0
    else:
        harmonic = (2.0 * p1 * p2) / (p1 + p2)
    return {
        "geometric": geometric,
        "arithmetic": arithmetic,
        "harmonic": harmonic,
        "official": "geometric",
        "production_candidate": PURCHASABILITY_CANDIDATE_NAME,
    }


def _calculate_phase_1(inputs: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    p_model = _safe_float(inputs.get("prob_cecchino"))
    edge_pct = _safe_float(inputs.get("edge_pct"))

    if p_model is None or edge_pct is None:
        return {
            "status": "unavailable",
            "score": None,
            "probability_strength_score": None,
            "edge_value_score": None,
            "component_scores": {
                "probability_strength": None,
                "edge_value": None,
            },
            "active_inputs": list(PHASE_1_ACTIVE_INPUTS),
            "diagnostic_only_inputs": list(PHASE_1_DIAGNOSTIC_INPUTS),
            "reason_codes": ["phase_1_active_inputs_missing"],
            "formula_version": PHASE_1_FORMULA_VERSION,
            "historical_reliability_used": False,
            "rating_used_as_weight": False,
            "score_acquisto_used_as_weight": False,
            "double_counting_prevented": True,
        }

    probability_strength_score = clamp(p_model * 100.0)
    positive_edge = max(edge_pct, 0.0)
    edge_value_score = clamp(positive_edge / 20.0 * 100.0)

    if edge_pct <= 0:
        edge_value_score = 0.0
        phase_1_raw = 0.0
        reason_codes.append("no_positive_value_detected")
    else:
        phase_1_raw = math.sqrt(probability_strength_score * edge_value_score)

    return {
        "status": "available",
        "score": _round2(phase_1_raw),
        "probability_strength_score": _round2(probability_strength_score),
        "edge_value_score": _round2(edge_value_score),
        "component_scores": {
            "probability_strength": _round2(probability_strength_score),
            "edge_value": _round2(edge_value_score),
        },
        "active_inputs": list(PHASE_1_ACTIVE_INPUTS),
        "diagnostic_only_inputs": list(PHASE_1_DIAGNOSTIC_INPUTS),
        "reason_codes": reason_codes,
        "formula_version": PHASE_1_FORMULA_VERSION,
        "historical_reliability_used": False,
        "rating_used_as_weight": False,
        "score_acquisto_used_as_weight": False,
        "double_counting_prevented": True,
        "_raw": phase_1_raw,
    }


def _favourite_alignment_score(alignment: Any) -> float | None:
    if alignment == "aligned":
        return 100.0
    if alignment in ("disagree", "partial"):
        return 50.0
    return None


def _calculate_phase_2(phase_2: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    component_scores: dict[str, float | None] = {}
    missing_components: list[str] = []

    sel_model = _safe_float(phase_2.get("model_context_probability"))
    opp_model = _safe_float(phase_2.get("opposition_pressure_model"))
    opp_book = _safe_float(phase_2.get("opposition_pressure_book"))

    if sel_model is None or opp_model is None:
        component_scores["model_opposition_support"] = None
        missing_components.append("model_opposition_support")
    else:
        component_scores["model_opposition_support"] = clamp(
            50.0 + 100.0 * (sel_model - opp_model)
        )

    if opp_book is None:
        component_scores["book_opposition_resistance"] = None
        missing_components.append("book_opposition_resistance")
    else:
        component_scores["book_opposition_resistance"] = clamp(
            100.0 * (1.0 - opp_book)
        )

    book_fav = phase_2.get("book_favourite")
    book_fav_sel = None
    if isinstance(book_fav, dict):
        book_fav_sel = book_fav.get("selection")
    comparators = phase_2.get("comparator_selections") or []
    if not isinstance(comparators, list):
        comparators = []

    if book_fav_sel and book_fav_sel in comparators:
        intensity = _safe_float(phase_2.get("favourite_intensity_book"))
        if intensity is None:
            component_scores["opposite_favourite_intensity"] = None
            missing_components.append("opposite_favourite_intensity")
        else:
            component_scores["opposite_favourite_intensity"] = clamp(
                100.0 * (1.0 - intensity)
            )
    else:
        component_scores["opposite_favourite_intensity"] = 100.0

    align_score = _favourite_alignment_score(phase_2.get("favourite_alignment"))
    if align_score is None:
        component_scores["favourite_alignment"] = None
        missing_components.append("favourite_alignment")
    else:
        component_scores["favourite_alignment"] = align_score

    abs_gap = _safe_float(phase_2.get("absolute_model_book_gap"))
    gap_dir = phase_2.get("gap_direction")
    if abs_gap is not None and abs_gap >= 0.10:
        if gap_dir == "positive" or (
            gap_dir is None
            and (_safe_float(phase_2.get("model_book_gap")) or 0) > 0
        ):
            reason_codes.append("model_materially_above_book")
        elif gap_dir == "negative" or (
            gap_dir is None
            and (_safe_float(phase_2.get("model_book_gap")) or 0) < 0
        ):
            reason_codes.append("model_materially_below_book")
        else:
            # gap grande ma direzione neutra/sconosciuta: entrambi i reason
            # non necessari — usa below se gap model_book negativo, else above
            mb = _safe_float(phase_2.get("model_book_gap"))
            if mb is not None and mb < 0:
                reason_codes.append("model_materially_below_book")
            elif mb is not None and mb > 0:
                reason_codes.append("model_materially_above_book")

    required_missing = [
        c for c in REQUIRED_PHASE_2_COMPONENTS if component_scores.get(c) is None
    ]
    if required_missing:
        return {
            "status": "unavailable",
            "score": None,
            "component_scores": component_scores,
            "configured_weights": dict(CONFIGURED_PHASE_2_WEIGHTS),
            "applied_weights": {},
            "missing_components": missing_components,
            "coverage_ratio": None,
            "reason_codes": reason_codes + ["phase_2_required_component_missing"],
            "formula_version": PHASE_2_FORMULA_VERSION,
            "model_book_gap_role": "descriptive_only",
            "large_gap_is_automatic_penalty": False,
            "large_gap_is_automatic_bonus": False,
            "_raw": None,
        }

    available_keys = [
        k
        for k, v in component_scores.items()
        if v is not None and k in CONFIGURED_PHASE_2_WEIGHTS
    ]
    weight_sum = sum(CONFIGURED_PHASE_2_WEIGHTS[k] for k in available_keys)
    applied_weights = {
        k: CONFIGURED_PHASE_2_WEIGHTS[k] / weight_sum for k in available_keys
    }
    phase_2_raw = sum(
        float(component_scores[k]) * applied_weights[k] for k in available_keys
    )
    coverage_ratio = weight_sum / sum(CONFIGURED_PHASE_2_WEIGHTS.values())

    optional_missing = [
        c for c in OPTIONAL_PHASE_2_COMPONENTS if c in missing_components
    ]
    status = "partial" if optional_missing else "available"
    if optional_missing:
        reason_codes.append("phase_2_optional_component_missing")

    return {
        "status": status,
        "score": _round2(phase_2_raw),
        "component_scores": {
            k: (_round2(v) if v is not None else None)
            for k, v in component_scores.items()
        },
        "configured_weights": dict(CONFIGURED_PHASE_2_WEIGHTS),
        "applied_weights": {k: _round2(v) for k, v in applied_weights.items()},
        "missing_components": missing_components,
        "coverage_ratio": _round2(coverage_ratio),
        "reason_codes": reason_codes,
        "formula_version": PHASE_2_FORMULA_VERSION,
        "model_book_gap_role": "descriptive_only",
        "large_gap_is_automatic_penalty": False,
        "large_gap_is_automatic_bonus": False,
        "_raw": phase_2_raw,
    }


def _build_contextual_reading(
    *,
    phase_2_feature: dict[str, Any],
    phase_1_score: float | None,
    model_support: float | None,
) -> str | None:
    opp_book = _safe_float(phase_2_feature.get("opposition_pressure_book"))
    if opp_book is not None and opp_book >= 0.65:
        return "La forza del segno opposto riduce la qualità del valore."
    if phase_2_feature.get("favourite_alignment") == "disagree":
        return (
            "Book e Cecchino individuano favoriti differenti; "
            "il disaccordo è descritto senza essere penalizzato automaticamente."
        )
    if model_support is not None and model_support >= 70:
        return (
            "Il modello sostiene la selezione rispetto ai mercati comparatori."
        )
    if phase_1_score is not None and phase_1_score == 0:
        return "La Fase 1 non rileva un vantaggio economico positivo."
    return None


def _build_reading(
    *,
    class_name: str | None,
    phase_2_feature: dict[str, Any],
    phase_1_score: float | None,
    model_support: float | None,
    unavailable_reason: str | None = None,
) -> str | None:
    if unavailable_reason:
        return unavailable_reason
    if not class_name:
        return None
    base = READING_BY_CLASS.get(class_name)
    if not base:
        return None
    contextual = _build_contextual_reading(
        phase_2_feature=phase_2_feature,
        phase_1_score=phase_1_score,
        model_support=model_support,
    )
    if contextual:
        return f"{base} {contextual}"
    return base


def _unavailable_reading(reason_codes: list[str]) -> str:
    if "opposition_context_not_supported" in reason_codes:
        return (
            "Mercato non supportato dal contesto di opposizione del candidato "
            "Acquistabilità v1 Preview."
        )
    if "snapshot_not_before_kickoff" in reason_codes:
        return (
            "Snapshot non pre-match: il candidato Acquistabilità non è "
            "disponibile dopo il calcio d’inizio."
        )
    if "phase_2_required_component_missing" in reason_codes:
        return (
            "Componenti obbligatori della Fase 2 assenti: score non calcolabile."
        )
    if "phase_1_active_inputs_missing" in reason_codes:
        return "Input attivi della Fase 1 assenti: score non calcolabile."
    if "feature_status_unavailable" in reason_codes:
        return "Feature layer non disponibile per questa selezione."
    return "Candidato Acquistabilità non disponibile per questa selezione."


def calculate_purchasability_candidate_item(
    feature_item: dict[str, Any],
) -> dict[str, Any]:
    market_key = feature_item.get("market_key") or feature_item.get("selection")
    selection = feature_item.get("selection") or market_key
    feature_status = feature_item.get("feature_status")
    data_quality = (
        feature_item.get("data_quality")
        if isinstance(feature_item.get("data_quality"), dict)
        else {}
    )
    phase_1_src = (
        feature_item.get("phase_1_value")
        if isinstance(feature_item.get("phase_1_value"), dict)
        else {}
    )
    phase_2_src = (
        feature_item.get("phase_2_quality")
        if isinstance(feature_item.get("phase_2_quality"), dict)
        else {}
    )
    inputs = (
        phase_1_src.get("inputs")
        if isinstance(phase_1_src.get("inputs"), dict)
        else {}
    )

    reason_codes: list[str] = []
    context_hooks = feature_item.get("context_hooks")

    unsupported = market_key not in SUPPORTED_CANDIDATE_MARKETS
    post_kickoff = data_quality.get("snapshot_before_kickoff") is False
    snapshot_verified = bool(data_quality.get("snapshot_timestamp_verified"))

    if unsupported:
        reason_codes.append("opposition_context_not_supported")
    if post_kickoff:
        reason_codes.append("snapshot_not_before_kickoff")
    if feature_status == "unavailable" and not unsupported and not post_kickoff:
        reason_codes.append("feature_status_unavailable")

    phase_1 = _calculate_phase_1(inputs)
    phase_2 = _calculate_phase_2(phase_2_src)

    # Merge feature phase payloads with scored fields (preserve inputs/evidence)
    phase_1_out = {
        **{k: v for k, v in phase_1_src.items() if k != "score"},
        "status": phase_1["status"],
        "score": phase_1["score"],
        "probability_strength_score": phase_1.get("probability_strength_score"),
        "edge_value_score": phase_1.get("edge_value_score"),
        "component_scores": phase_1.get("component_scores"),
        "active_inputs": phase_1.get("active_inputs"),
        "diagnostic_only_inputs": phase_1.get("diagnostic_only_inputs"),
        "reason_codes": phase_1.get("reason_codes") or [],
        "formula_version": PHASE_1_FORMULA_VERSION,
        "historical_reliability_used": False,
        "rating_used_as_weight": False,
        "score_acquisto_used_as_weight": False,
        "double_counting_prevented": True,
    }
    # Keep dependency_metadata from features if present
    if "dependency_metadata" not in phase_1_out and phase_1_src.get(
        "dependency_metadata"
    ):
        phase_1_out["dependency_metadata"] = phase_1_src["dependency_metadata"]

    phase_2_out = {
        **{k: v for k, v in phase_2_src.items() if k != "score"},
        "status": phase_2["status"],
        "score": phase_2["score"],
        "component_scores": phase_2.get("component_scores"),
        "configured_weights": phase_2.get("configured_weights"),
        "applied_weights": phase_2.get("applied_weights"),
        "missing_components": phase_2.get("missing_components"),
        "coverage_ratio": phase_2.get("coverage_ratio"),
        "reason_codes": phase_2.get("reason_codes") or [],
        "formula_version": PHASE_2_FORMULA_VERSION,
        "model_book_gap_role": "descriptive_only",
        "large_gap_is_automatic_penalty": False,
        "large_gap_is_automatic_bonus": False,
    }

    reason_codes.extend(phase_1.get("reason_codes") or [])
    reason_codes.extend(phase_2.get("reason_codes") or [])

    p1_raw = phase_1.get("_raw")
    p2_raw = phase_2.get("_raw")
    core_ok = (
        p1_raw is not None
        and p2_raw is not None
        and phase_1["status"] != "unavailable"
        and phase_2["status"] != "unavailable"
    )

    force_unavailable = (
        unsupported
        or post_kickoff
        or feature_status == "unavailable"
        or not core_ok
    )

    if force_unavailable:
        # Deduplicate reason codes preserving order
        seen: set[str] = set()
        uniq_reasons: list[str] = []
        for r in reason_codes:
            if r and r not in seen:
                seen.add(r)
                uniq_reasons.append(r)
        reading = _unavailable_reading(uniq_reasons)
        item = {
            "version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_FEATURE_VERSION,
            "candidate_version": PURCHASABILITY_CANDIDATE_VERSION,
            "candidate_name": PURCHASABILITY_CANDIDATE_NAME,
            "feature_status": feature_status,
            "status": "unavailable",
            "calculation_quality": None,
            "score": None,
            "raw_score": None,
            "class": None,
            "reading": reading,
            "market_key": market_key,
            "selection": selection,
            "phase_1_value": phase_1_out,
            "phase_2_quality": phase_2_out,
            "final_combination": {
                "official": "geometric",
                "formula_version": FINAL_FORMULA_VERSION,
                "geometric": None,
                "arithmetic": None,
                "harmonic": None,
            },
            "comparator_formulas": {
                "geometric": "sqrt(phase_1 * phase_2)",
                "arithmetic": "0.5 * phase_1 + 0.5 * phase_2",
                "harmonic": "2 * phase_1 * phase_2 / (phase_1 + phase_2)",
            },
            "context_hooks": context_hooks,
            "reason_codes": uniq_reasons,
            "data_quality": data_quality,
            "score_metadata": {
                "future_context_modules_used": False,
                "future_context_modules": ["balance_v5", "goal_intensity_v5"],
                "historical_reliability_used": False,
                "rating_used_as_weight": False,
                "score_acquisto_used_as_weight": False,
                "official_combiner": "geometric",
            },
        }
        return make_json_safe(item)

    combiners = compare_purchasability_combiners(
        phase_1_score=float(p1_raw),
        phase_2_score=float(p2_raw),
    )
    raw_final = float(combiners["geometric"])
    rounded = int(round(clamp(raw_final)))
    class_name = map_score_to_class(rounded)

    is_partial = (
        feature_status == "partial"
        or phase_2["status"] == "partial"
        or not snapshot_verified
    )
    top_status = "partial" if is_partial else "available"
    calculation_quality = "partial" if is_partial else "full"

    model_support = (phase_2.get("component_scores") or {}).get(
        "model_opposition_support"
    )
    reading = _build_reading(
        class_name=class_name,
        phase_2_feature=phase_2_src,
        phase_1_score=phase_1.get("score"),
        model_support=_safe_float(model_support),
    )

    seen2: set[str] = set()
    uniq2: list[str] = []
    for r in reason_codes:
        if r and r not in seen2:
            seen2.add(r)
            uniq2.append(r)

    item = {
        "version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_FEATURE_VERSION,
        "candidate_version": PURCHASABILITY_CANDIDATE_VERSION,
        "candidate_name": PURCHASABILITY_CANDIDATE_NAME,
        "feature_status": feature_status,
        "status": top_status,
        "calculation_quality": calculation_quality,
        "score": rounded,
        "raw_score": _round2(raw_final),
        "class": class_name,
        "reading": reading,
        "market_key": market_key,
        "selection": selection,
        "phase_1_value": phase_1_out,
        "phase_2_quality": phase_2_out,
        "final_combination": {
            "official": "geometric",
            "formula_version": FINAL_FORMULA_VERSION,
            "geometric": _round2(combiners["geometric"]),
            "arithmetic": _round2(combiners["arithmetic"]),
            "harmonic": _round2(combiners["harmonic"]),
            "raw_final_score": raw_final,
            "rounded_final_score": rounded,
        },
        "comparator_formulas": {
            "geometric": "sqrt(phase_1 * phase_2)",
            "arithmetic": "0.5 * phase_1 + 0.5 * phase_2",
            "harmonic": "2 * phase_1 * phase_2 / (phase_1 + phase_2)",
        },
        "context_hooks": context_hooks,
        "reason_codes": uniq2,
        "data_quality": data_quality,
        "score_metadata": {
            "future_context_modules_used": False,
            "future_context_modules": ["balance_v5", "goal_intensity_v5"],
            "historical_reliability_used": False,
            "rating_used_as_weight": False,
            "score_acquisto_used_as_weight": False,
            "official_combiner": "geometric",
            "production_candidate": PURCHASABILITY_CANDIDATE_NAME,
        },
    }
    return make_json_safe(item)


def calculate_purchasability_candidate_batch(
    feature_batch: dict[str, Any],
) -> dict[str, Any]:
    items_in = feature_batch.get("items") if isinstance(feature_batch, dict) else None
    if not isinstance(items_in, list):
        items_in = []

    items: list[dict[str, Any]] = [
        calculate_purchasability_candidate_item(it)
        for it in items_in
        if isinstance(it, dict)
    ]

    available = partial = unavailable = 0
    class_dist = {c: 0 for c in CLASS_ORDER}
    scores: list[float] = []
    supported: list[str] = []
    unsupported: list[str] = []

    for it in items:
        st = it.get("status")
        if st == "available":
            available += 1
        elif st == "partial":
            partial += 1
        else:
            unavailable += 1
        cls = it.get("class")
        if cls in class_dist:
            class_dist[cls] += 1
        sc = it.get("score")
        if sc is not None:
            scores.append(float(sc))
        mk = it.get("market_key")
        if mk in SUPPORTED_CANDIDATE_MARKETS:
            supported.append(str(mk))
        elif mk:
            unsupported.append(str(mk))

    if not items:
        batch_status = "unavailable"
    elif unavailable == len(items):
        batch_status = "unavailable"
    elif available == len(items):
        batch_status = "ok"
    else:
        batch_status = "partial"

    payload = {
        "status": batch_status,
        "version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_FEATURE_VERSION,
        "candidate_version": PURCHASABILITY_CANDIDATE_VERSION,
        "candidate_name": PURCHASABILITY_CANDIDATE_NAME,
        "today_fixture_id": feature_batch.get("today_fixture_id"),
        "items": items,
        "summary": {
            "total": len(items),
            "available": available,
            "partial": partial,
            "unavailable": unavailable,
            "class_distribution": class_dist,
            "score_min": min(scores) if scores else None,
            "score_max": max(scores) if scores else None,
            "score_mean": (
                _round2(statistics.mean(scores)) if scores else None
            ),
            "supported_markets": sorted(set(supported)),
            "unsupported_markets": sorted(set(unsupported)),
        },
        "official_combiner": "geometric",
        "historical_reliability_used": False,
        "rating_used_as_weight": False,
        "signals_integration": False,
        "ui_integration": False,
        "db_persistence": False,
        "no_db_writes": True,
    }
    safe = make_json_safe(payload)
    json.dumps(safe, allow_nan=False)
    return safe


def build_purchasability_candidate_for_fixture(fixture: Any) -> dict[str, Any]:
    features = build_purchasability_features_for_fixture(fixture)
    return calculate_purchasability_candidate_batch(features)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def audit_candidate_independence(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Diagnostico indipendenza candidato vs Rating/Score — no auto-tuning."""
    compared = 0
    equals_rating = 0
    equals_score_acq = 0
    abs_diffs: list[float] = []
    cand_scores: list[float] = []
    ratings: list[float] = []
    edges: list[float] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        score = _safe_float(it.get("score"))
        if score is None:
            continue
        phase1 = it.get("phase_1_value") if isinstance(it.get("phase_1_value"), dict) else {}
        inputs = phase1.get("inputs") if isinstance(phase1.get("inputs"), dict) else {}
        rating = _safe_float(inputs.get("rating"))
        score_acq = _safe_float(inputs.get("score_acquisto"))
        edge = _safe_float(inputs.get("edge_pct"))
        compared += 1
        cand_scores.append(score)
        if rating is not None:
            if abs(score - rating) < 1e-9:
                equals_rating += 1
            abs_diffs.append(abs(score - rating))
            ratings.append(rating)
        if score_acq is not None and abs(score - score_acq) < 1e-9:
            equals_score_acq += 1
        if edge is not None:
            edges.append(edge)

    # Align edges with cand_scores only when both present — rebuild paired lists
    paired_edge_c: list[float] = []
    paired_edge_e: list[float] = []
    paired_rating_c: list[float] = []
    paired_rating_r: list[float] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        score = _safe_float(it.get("score"))
        if score is None:
            continue
        phase1 = it.get("phase_1_value") if isinstance(it.get("phase_1_value"), dict) else {}
        inputs = phase1.get("inputs") if isinstance(phase1.get("inputs"), dict) else {}
        rating = _safe_float(inputs.get("rating"))
        edge = _safe_float(inputs.get("edge_pct"))
        if rating is not None:
            paired_rating_c.append(score)
            paired_rating_r.append(rating)
        if edge is not None:
            paired_edge_c.append(score)
            paired_edge_e.append(edge)

    return make_json_safe(
        {
            "compared_items": compared,
            "exact_score_equals_rating_count": equals_rating,
            "exact_score_equals_score_acquisto_count": equals_score_acq,
            "candidate_rating_mean_absolute_difference": (
                _round2(statistics.mean(abs_diffs)) if abs_diffs else None
            ),
            "candidate_rating_correlation": _pearson(
                paired_rating_c, paired_rating_r
            ),
            "candidate_edge_correlation": _pearson(paired_edge_c, paired_edge_e),
            "independence_invariants": {
                "candidate_formula_contains_rating": False,
                "candidate_formula_contains_score_acquisto": False,
                "candidate_formula_contains_historical_reliability": False,
                "rating_variation_alone_does_not_change_candidate": True,
                "historical_reliability_variation_alone_does_not_change_candidate": True,
            },
            "historical_reliability_imported": False,
        }
    )
