"""Orchestrazione Cecchino Purchasability V3.5 — gate, componenti, candidate A/B/C/D, batch."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_REGISTRY_STATUS,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_fair_book import (
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
)
from app.services.cecchino.cecchino_purchasability_v35_components import (
    compute_executable_value,
    compute_information_quality,
    compute_market_disagreement,
    compute_structural_coherence,
    delta_logit,
)
from app.services.cecchino.cecchino_purchasability_v35_config import (
    CANDIDATE_IDS,
    CANDIDATE_NAMES,
    CANDIDATE_WEIGHTS,
    RELATION_REGISTRY_VERSION,
    dependency_meta,
    market_label_for,
    version_meta,
)
from app.services.cecchino.cecchino_purchasability_v35_features import (
    build_market_input_context,
    evaluate_v35_gate,
    resolve_fair_book_probability,
    verify_pre_match_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_relations import (
    relation_registry_audit,
)
from app.services.cecchino.cecchino_purchasability_v35_utils import (
    classify_score_v35,
    round_score_v35,
)

SUPPORTED_V35_MARKETS = frozenset(PANEL_MARKET_KEYS)


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


def _round4(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )


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
        if mk in SUPPORTED_V35_MARKETS and mk not in seen:
            ordered.append(mk)
            seen.add(mk)
    for mk in PANEL_MARKET_KEYS:
        if mk not in seen:
            ordered.append(mk)
            seen.add(mk)
    return ordered


def score_candidate(
    components: dict[str, float | None],
    candidate_key: str,
) -> dict[str, Any]:
    """Weighted normalized mean with S renormalization when unavailable."""
    weights = dict(CANDIDATE_WEIGHTS[candidate_key])
    available: dict[str, float] = {}
    missing: list[str] = []
    for comp_key, weight in weights.items():
        val = components.get(comp_key)
        if val is None:
            missing.append(comp_key)
        else:
            available[comp_key] = float(val)

    if not available:
        return {
            "candidate_id": CANDIDATE_IDS[candidate_key],
            "candidate_name": CANDIDATE_NAMES[candidate_key],
            "raw_score": None,
            "score": None,
            "class": None,
            "effective_weights": {},
            "missing_components": missing,
            "configured_weights": weights,
        }

    denom = sum(weights[k] for k in available)
    if denom <= 0:
        raw = None
    else:
        raw = sum(weights[k] * available[k] for k in available) / denom

    effective = {k: _round4(weights[k] / denom) for k in available}
    score_int = round_score_v35(raw) if raw is not None else None

    return {
        "candidate_id": CANDIDATE_IDS[candidate_key],
        "candidate_name": CANDIDATE_NAMES[candidate_key],
        "raw_score": _round2(raw) if raw is not None else None,
        "score": score_int,
        "class": classify_score_v35(score_int),
        "effective_weights": effective,
        "missing_components": missing,
        "configured_weights": weights,
    }


def calculate_purchasability_v35_item(
    market_key: str,
    row: dict[str, Any],
    by_mk: dict[str, dict[str, Any]],
    *,
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None] | None,
    fixture_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vmeta = version_meta()
    fair_info = fair_by.get(market_key)
    ctx = build_market_input_context(
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

    base_item: dict[str, Any] = {
        **vmeta,
        "registry_status": PURCHASABILITY_V35_REGISTRY_STATUS,
        "market_key": market_key,
        "label": market_label_for(market_key),
        "status": gate["item_status"],
        "gate_status": gate["gate_status"],
        "pre_match_only": True,
        "contains_post_match_fields": False,
        "gate": gate,
        "input": {
            "execution_quote": ctx["execution"].get("execution_quote"),
            "execution_quote_real": ctx["execution"].get("execution_quote_real"),
            "execution_quote_source": ctx["execution"].get("execution_quote_source"),
            "probability_cecchino": ctx["probability_cecchino"],
            "fair_book_probability": ctx["fair_book_probability"],
            "rating": _safe_float(ctx["row"].get("rating")),
            "overround": ctx["overround"],
            "book_fallback_used": ctx["book_fallback_used"],
            "fair_probability_may_be_derived": ctx["fair_probability_may_be_derived"],
        },
        "components": {
            "executable_value": None,
            "market_disagreement": None,
            "structural_coherence": None,
            "information_quality": None,
        },
        "candidates": {},
        "diagnostics": {
            "edge_pct": ctx["edge_pct_diagnostic"],
            "vantaggio_prob": ctx["vantaggio_prob_diagnostic"],
            "hours_to_kickoff": ctx["hours_to_kickoff"],
            "snapshot_age_used_in_score": False,
        },
        "dependency_meta": dependency_meta(),
    }

    if gate["gate_status"] != "passed":
        base_item["candidates"] = {
            k: score_candidate({}, k) for k in ("A", "B", "C", "D")
        }
        for ck in base_item["candidates"]:
            base_item["candidates"][ck]["raw_score"] = None
            base_item["candidates"][ck]["score"] = None
            base_item["candidates"][ck]["class"] = None
        return make_json_safe(base_item)

    p_cec = float(gate["probability_cecchino"])
    p_fair = float(gate["fair_book_probability"])
    ev = float(gate["expected_value"])

    v_block = compute_executable_value(ev)
    d_block = compute_market_disagreement(p_cec, p_fair)
    s_block = compute_structural_coherence(
        market_key,
        by_mk=by_mk,
        fair_by=fair_by,
        model_probs=model_probs,
    )
    q_block = compute_information_quality(
        overround=ctx["overround"],
        book_fallback_used=ctx["book_fallback_used"],
        fair_probability_may_be_derived=ctx["fair_probability_may_be_derived"],
        delta_logit_value=d_block["delta_logit"],
        hours_to_kickoff=ctx["hours_to_kickoff"],
    )

    base_item["components"] = {
        "executable_value": v_block,
        "market_disagreement": d_block,
        "structural_coherence": s_block,
        "information_quality": q_block,
    }

    comp_scores = {
        "V": v_block["score"],
        "D": d_block["score"],
        "S": s_block["score"],
        "Q": q_block["score"],
    }

    base_item["candidates"] = {
        k: score_candidate(comp_scores, k) for k in ("A", "B", "C", "D")
    }
    base_item["diagnostics"]["expected_value"] = ev
    base_item["diagnostics"]["delta_logit"] = d_block["delta_logit"]

    return make_json_safe(base_item)


def calculate_purchasability_v35_batch(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Batch puro pre-match — tutti i 19 mercati panel."""
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

    items = [
        calculate_purchasability_v35_item(
            mk,
            by_mk.get(mk) or {},
            by_mk,
            fair_by=fair_by,
            model_probs=model_probs,
            fixture_meta=meta,
        )
        for mk in ordered
    ]

    vmeta = version_meta()
    return make_json_safe(
        {
            **vmeta,
            "registry_status": PURCHASABILITY_V35_REGISTRY_STATUS,
            "status": "ok" if items else "unavailable",
            "relation_registry_version": RELATION_REGISTRY_VERSION,
            "relation_registry": relation_registry_audit(),
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
                "supported_markets": len(SUPPORTED_V35_MARKETS),
            },
            "pre_match_only": True,
            "pre_match_verified": pre_match_check["verified"],
            "contains_post_match_fields": False,
            "dependency_meta": dependency_meta(),
        }
    )


__all__ = [
    "SUPPORTED_V35_MARKETS",
    "calculate_purchasability_v35_batch",
    "calculate_purchasability_v35_item",
    "score_candidate",
    "delta_logit",
]
