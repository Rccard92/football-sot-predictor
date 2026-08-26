"""Orchestrazione Cecchino Purchasability V3.5 Structural V2 — singolo indice."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_REFERENCE_ID,
    PURCHASABILITY_V35_V2_REFERENCE_LABEL,
    PURCHASABILITY_V35_V2_REGISTRY_STATUS,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_fair_book import (
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_components import (
    compute_acquisition_core,
    compute_adjusted_and_final,
    compute_base_rate_reliability,
    compute_executable_value_v2,
    compute_information_quality_v2,
    compute_market_disagreement_v2,
    compute_structural_coherence_v2,
    compute_value_core,
    structural_factor_from_s,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    RELATION_REGISTRY_VERSION,
    dependency_meta,
    frozen_config_v35_v2,
    market_label_for,
    version_meta,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_features import (
    build_market_input_context_v2,
    evaluate_v35_gate,
    evaluate_v35_v2_gate_from_inputs,
    verify_pre_match_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_relations import (
    relation_registry_audit,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_utils import (
    classify_score_v2,
    round_score_v2,
)

SUPPORTED_V35_V2_MARKETS = frozenset(PANEL_MARKET_KEYS)


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
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _panel_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_mk: dict[str, dict[str, Any]] = {}
    for row in rows:
        mk = str(row.get("market_key") or row.get("segno") or "").strip()
        if mk:
            by_mk[mk] = row
    return by_mk


def _ordered_markets(rows: list[dict[str, Any]]) -> list[str]:
    panel_order = [
        str(r.get("market_key") or r.get("segno"))
        for r in rows
        if (r.get("market_key") or r.get("segno"))
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for mk in panel_order:
        if mk in SUPPORTED_V35_V2_MARKETS and mk not in seen:
            ordered.append(mk)
            seen.add(mk)
    for mk in PANEL_MARKET_KEYS:
        if mk not in seen:
            ordered.append(mk)
            seen.add(mk)
    return ordered


def _probs_map_from_contexts(
    by_mk: dict[str, dict[str, Any]],
    *,
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None] | None,
    fixture_meta: dict[str, Any] | None,
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for mk in PANEL_MARKET_KEYS:
        ctx = build_market_input_context_v2(
            row=by_mk.get(mk) or {},
            fair_info=fair_by.get(mk),
            model_probs=model_probs,
            market_key=mk,
            fixture_meta=fixture_meta,
        )
        out[mk] = {
            "probability_cecchino": ctx["probability_cecchino"],
            "fair_book_probability": ctx["fair_book_probability"],
        }
    return out


def score_structural_v2_from_components(
    *,
    v_score: float,
    d_score: float,
    r_score: float,
    s_block: dict[str, Any],
    q_block: dict[str, Any],
) -> dict[str, Any]:
    vc = compute_value_core(v_score, d_score)
    ac = compute_acquisition_core(vc["value_core"], r_score)
    s_factor = structural_factor_from_s(s_block)
    q_factor = float(q_block["quality_factor"])
    finals = compute_adjusted_and_final(
        acquisition_core=ac["acquisition_core"],
        structural_factor=s_factor,
        quality_factor=q_factor,
    )
    score_int = round_score_v2(finals["final_score_raw"])
    return {
        "reference_id": PURCHASABILITY_V35_V2_REFERENCE_ID,
        "label": PURCHASABILITY_V35_V2_REFERENCE_LABEL,
        "value_core": _round2(vc["value_core"]),
        "V_contribution": _round2(vc["V_contribution"]),
        "D_contribution": _round2(vc["D_contribution"]),
        "acquisition_core": _round2(ac["acquisition_core"]),
        "structural_factor": s_factor,
        "quality_factor": q_factor,
        "adjusted_confidence": _round2(finals["adjusted_confidence"]),
        "raw_score": _round2(finals["final_score_raw"]),
        "score": score_int,
        "class": classify_score_v2(score_int),
        "structural_missing_penalty_applied": bool(
            s_block.get("structural_missing_penalty_applied")
        ),
    }


def calculate_purchasability_v35_v2_item_from_prematch(
    market_key: str,
    *,
    gate: dict[str, Any],
    input_payload: dict[str, Any],
    probs_by_market: dict[str, dict[str, float | None]],
) -> dict[str, Any]:
    """Calcolo item V2 da soli input pre-match (batch KPI o replay CSV)."""
    vmeta = version_meta()
    base_item: dict[str, Any] = {
        **vmeta,
        "registry_status": PURCHASABILITY_V35_V2_REGISTRY_STATUS,
        "market_key": market_key,
        "label": market_label_for(market_key),
        "status": gate["item_status"],
        "gate_status": gate["gate_status"],
        "pre_match_only": True,
        "contains_post_match_fields": False,
        "gate": gate,
        "input": input_payload,
        "components": {
            "executable_value": None,
            "market_disagreement": None,
            "base_rate_reliability": None,
            "structural_coherence": None,
            "information_quality": None,
        },
        "value_core": None,
        "acquisition_core": None,
        "reference": {
            "id": PURCHASABILITY_V35_V2_REFERENCE_ID,
            "label": PURCHASABILITY_V35_V2_REFERENCE_LABEL,
            "score": None,
            "raw_score": None,
            "class": None,
        },
        "dependency_meta": dependency_meta(),
    }

    if gate.get("gate_status") != "passed":
        return make_json_safe(base_item)

    p_cec = float(gate["probability_cecchino"])
    p_fair = float(gate["fair_book_probability"])
    ev = float(gate["expected_value"])

    v_block = compute_executable_value_v2(ev)
    d_block = compute_market_disagreement_v2(p_cec, p_fair)
    r_block = compute_base_rate_reliability(p_cec, p_fair)
    s_block = compute_structural_coherence_v2(
        market_key, probs_by_market=probs_by_market
    )
    q_block = compute_information_quality_v2(
        overround=input_payload.get("overround"),
        book_fallback_used=bool(input_payload.get("book_fallback_used")),
        fair_probability_may_be_derived=bool(
            input_payload.get("fair_probability_may_be_derived")
        ),
        delta_logit_value=float(d_block["delta_logit"]),
    )
    scored = score_structural_v2_from_components(
        v_score=float(v_block["score"]),
        d_score=float(d_block["score"]),
        r_score=float(r_block["score"]),
        s_block=s_block,
        q_block=q_block,
    )

    base_item["components"] = {
        "executable_value": v_block,
        "market_disagreement": d_block,
        "base_rate_reliability": r_block,
        "structural_coherence": s_block,
        "information_quality": q_block,
    }
    base_item["value_core"] = scored["value_core"]
    base_item["acquisition_core"] = scored["acquisition_core"]
    base_item["structural_factor"] = scored["structural_factor"]
    base_item["quality_factor"] = scored["quality_factor"]
    base_item["adjusted_confidence"] = scored["adjusted_confidence"]
    base_item["structural_missing_penalty_applied"] = scored[
        "structural_missing_penalty_applied"
    ]
    base_item["reference"] = {
        "id": scored["reference_id"],
        "label": scored["label"],
        "score": scored["score"],
        "raw_score": scored["raw_score"],
        "class": scored["class"],
    }
    base_item["score"] = scored["score"]
    base_item["raw_score"] = scored["raw_score"]
    base_item["class"] = scored["class"]
    return make_json_safe(base_item)


def calculate_purchasability_v35_v2_item(
    market_key: str,
    row: dict[str, Any],
    by_mk: dict[str, dict[str, Any]],
    *,
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None] | None,
    fixture_meta: dict[str, Any] | None = None,
    probs_by_market: dict[str, dict[str, float | None]] | None = None,
) -> dict[str, Any]:
    fair_info = fair_by.get(market_key)
    ctx = build_market_input_context_v2(
        row=row,
        fair_info=fair_info,
        model_probs=model_probs,
        market_key=market_key,
        fixture_meta=fixture_meta,
    )
    gate = evaluate_v35_gate(
        row=ctx["row"],
        fair_info=fair_info,
        exec_info=ctx["execution"],
        probability_cecchino=ctx["probability_cecchino"],
        fair_book_probability=ctx["fair_book_probability"],
        fixture_meta=fixture_meta,
    )
    if probs_by_market is None:
        probs_by_market = _probs_map_from_contexts(
            by_mk,
            fair_by=fair_by,
            model_probs=model_probs,
            fixture_meta=fixture_meta,
        )
    input_payload = {
        "execution_quote": ctx["execution"].get("execution_quote"),
        "execution_quote_real": ctx["execution"].get("execution_quote_real"),
        "execution_quote_source": ctx["execution"].get("execution_quote_source"),
        "probability_cecchino": ctx["probability_cecchino"],
        "fair_book_probability": ctx["fair_book_probability"],
        "rating": _safe_float(ctx["row"].get("rating")),
        "overround": ctx["overround"],
        "book_fallback_used": ctx["book_fallback_used"],
        "fair_probability_may_be_derived": ctx["fair_probability_may_be_derived"],
    }
    return calculate_purchasability_v35_v2_item_from_prematch(
        market_key,
        gate=gate,
        input_payload=input_payload,
        probs_by_market=probs_by_market,
    )


def calculate_purchasability_v35_v2_batch(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _panel_rows(kpi_panel)
    by_mk = _index_rows(rows)
    meta = dict(fixture_meta or {})
    pre_match_check = verify_pre_match_snapshot(meta)
    fair_by = resolve_fair_book_for_panel_rows(
        rows,
        today_fixture_id=meta.get("today_fixture_id"),
        snapshot_at=meta.get("snapshot_at"),
    )
    model_probs = build_model_context_probability_map(rows)
    ordered = _ordered_markets(rows)
    probs_by_market = _probs_map_from_contexts(
        by_mk,
        fair_by=fair_by,
        model_probs=model_probs,
        fixture_meta=meta,
    )
    items = [
        calculate_purchasability_v35_v2_item(
            mk,
            by_mk.get(mk) or {},
            by_mk,
            fair_by=fair_by,
            model_probs=model_probs,
            fixture_meta=meta,
            probs_by_market=probs_by_market,
        )
        for mk in ordered
    ]
    vmeta = version_meta()
    return make_json_safe(
        {
            **vmeta,
            "registry_status": PURCHASABILITY_V35_V2_REGISTRY_STATUS,
            "status": "ok" if items else "unavailable",
            "relation_registry_version": RELATION_REGISTRY_VERSION,
            "relation_registry": relation_registry_audit(),
            "frozen_config": frozen_config_v35_v2(),
            "reference": {
                "id": PURCHASABILITY_V35_V2_REFERENCE_ID,
                "label": PURCHASABILITY_V35_V2_REFERENCE_LABEL,
            },
            "items": items,
            "fixture_meta": {
                "today_fixture_id": meta.get("today_fixture_id"),
                "kickoff": meta.get("kickoff"),
                "snapshot_at": meta.get("snapshot_at"),
            },
            "summary": {
                "rows_total": len(items),
                "score_count": sum(1 for it in items if it.get("status") == "score"),
                "gate_failed_count": sum(
                    1 for it in items if it.get("status") == "gate_failed"
                ),
                "non_calculable_count": sum(
                    1 for it in items if it.get("status") == "not_calculable"
                ),
                "supported_markets": len(SUPPORTED_V35_V2_MARKETS),
            },
            "pre_match_only": True,
            "pre_match_verified": pre_match_check["verified"],
            "contains_post_match_fields": False,
            "dependency_meta": dependency_meta(),
        }
    )


__all__ = [
    "SUPPORTED_V35_V2_MARKETS",
    "calculate_purchasability_v35_v2_batch",
    "calculate_purchasability_v35_v2_item",
    "calculate_purchasability_v35_v2_item_from_prematch",
    "evaluate_v35_v2_gate_from_inputs",
    "score_structural_v2_from_components",
]
