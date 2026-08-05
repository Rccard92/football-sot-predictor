"""Confronto diagnostico V3 vs V3.1 e riepilogo shadow."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_comparison_with_v3(
    v31_item: dict[str, Any],
    v3_item: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(v3_item, dict):
        v3_status = "unsupported_market"
        v3_score = None
        v3_class = None
    else:
        gate = str(v3_item.get("gate_status") or "")
        if gate == "unsupported_market" or "unsupported_market" in (
            v3_item.get("reason_codes") or []
        ):
            v3_status = "unsupported_market"
        else:
            v3_status = str(v3_item.get("status") or "unavailable")
        v3_score = v3_item.get("score")
        v3_class = v3_item.get("class")

    v31_status = str(v31_item.get("status") or "non_calculable")
    v31_score = v31_item.get("score")
    v31_class = v31_item.get("class")

    score_delta = None
    if v3_score is not None and v31_score is not None:
        try:
            score_delta = int(v31_score) - int(v3_score)
        except (TypeError, ValueError):
            score_delta = None

    reasons: list[str] = []
    if v3_status == "unsupported_market" and v31_status != "unsupported_market":
        reasons.append("market_now_supported_in_v31")
    if v31_status == "non_calculable" and "derived_quote_not_executable" in (
        v31_item.get("reason_codes") or []
    ):
        reasons.append("derived_quote_blocks_v31")
    if v31_status == "non_calculable" and "historical_sample_insufficient" in (
        v31_item.get("reason_codes") or []
    ):
        reasons.append("historical_blocks_v31")
    hist = v31_item.get("historical") if isinstance(v31_item.get("historical"), dict) else {}
    if hist.get("historical_factor") is not None and v31_score is not None:
        reasons.append("historical_factor_applied")
    if v31_status == "gate_failed" and "rating_below_purchase_scope" in (
        v31_item.get("reason_codes") or []
    ):
        reasons.append("rating_gate_v31")
    if not reasons and score_delta is not None and score_delta != 0:
        reasons.append("score_formula_delta")

    return {
        "v3_status": v3_status,
        "v3_score": v3_score,
        "v3_class": v3_class,
        "v31_status": v31_status,
        "v31_score": v31_score,
        "v31_class": v31_class,
        "score_delta": score_delta,
        "class_changed": (v3_class != v31_class) if v3_class or v31_class else False,
        "status_changed": v3_status != v31_status,
        "main_change_reasons": reasons,
    }


def build_shadow_summary(
    items: list[dict[str, Any]],
    *,
    v3_items_by_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    v3_map = v3_items_by_market or {}
    market_dist: Counter[str] = Counter()
    class_dist: Counter[str] = Counter()
    reason_dist: Counter[str] = Counter()

    score_count = 0
    gate_failed = 0
    non_calc = 0
    derived = 0
    missing_quote = 0
    incomplete_fair = 0
    hist_insufficient = 0
    v3_supported = 0
    v31_supported = 0
    v3_scores: list[float] = []
    v31_scores: list[float] = []
    deltas: list[float] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        mk = str(it.get("market_key") or "")
        market_dist[mk] += 1
        v31_supported += 1
        status = it.get("status")
        if status == "score":
            score_count += 1
            sc = _safe_float(it.get("score"))
            if sc is not None:
                v31_scores.append(sc)
            klass = it.get("class")
            if klass:
                class_dist[str(klass)] += 1
        elif status == "gate_failed":
            gate_failed += 1
        elif status == "non_calculable":
            non_calc += 1
            for code in it.get("reason_codes") or []:
                reason_dist[str(code)] += 1
                if code == "derived_quote_not_executable":
                    derived += 1
                elif code == "book_quote_unavailable":
                    missing_quote += 1
                elif code in (
                    "fair_book_complete_set_incomplete",
                    "fair_book_probability_unavailable",
                ):
                    incomplete_fair += 1
                elif code == "historical_sample_insufficient":
                    hist_insufficient += 1

        v3 = v3_map.get(mk)
        if isinstance(v3, dict):
            gate = str(v3.get("gate_status") or "")
            if gate != "unsupported_market" and "unsupported_market" not in (
                v3.get("reason_codes") or []
            ):
                v3_supported += 1
            v3s = _safe_float(v3.get("score"))
            v31s = _safe_float(it.get("score"))
            if v3s is not None:
                v3_scores.append(v3s)
            if v3s is not None and v31s is not None:
                deltas.append(v31s - v3s)

    def _avg(xs: list[float]) -> float | None:
        if not xs:
            return None
        return round(sum(xs) / len(xs), 4)

    return {
        "rows_total": len(items),
        "rows_v3_supported": v3_supported,
        "rows_v31_supported": v31_supported,
        "scores_produced": score_count,
        "gate_failed": gate_failed,
        "non_calculable": non_calc,
        "quotes_absent": missing_quote,
        "quotes_derived": derived,
        "fair_set_incomplete": incomplete_fair,
        "historical_insufficient": hist_insufficient,
        "distribution_by_market": dict(market_dist),
        "distribution_by_class": dict(class_dist),
        "distribution_by_reason": dict(reason_dist),
        "mean_score_v3": _avg(v3_scores),
        "mean_score_v31": _avg(v31_scores),
        "mean_delta_comparable": _avg(deltas),
        "comparable_rows": len(deltas),
    }


def attach_comparisons_and_summary(
    batch: dict[str, Any],
    *,
    v3_items_by_market: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    items = list(batch.get("items") or [])
    enriched: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        mk = str(it.get("market_key") or "")
        comp = build_comparison_with_v3(it, v3_items_by_market.get(mk))
        row = dict(it)
        row["comparison_with_v3"] = comp
        enriched.append(row)
    batch = dict(batch)
    batch["items"] = enriched
    batch["shadow_summary"] = build_shadow_summary(
        enriched, v3_items_by_market=v3_items_by_market
    )
    return batch
