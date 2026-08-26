"""Feature/gate helpers V3.5 Structural V2 — reuse V1 gate math, V2 forbidden set."""

from __future__ import annotations

import math
from typing import Any

from app.services.cecchino.cecchino_purchasability_v35_features import (
    build_market_input_context as _build_market_input_context_v1,
    compute_expected_value,
    evaluate_v35_gate,
    is_valid_open_probability,
    resolve_execution_quote_v35,
    resolve_probability_cecchino,
    verify_pre_match_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    RATING_MIN_GATE,
    V35_V2_FORBIDDEN_INPUT_KEYS,
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


def sanitize_kpi_row_v2(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in V35_V2_FORBIDDEN_INPUT_KEYS:
            continue
        out[key] = value
    mk = out.get("market_key") or row.get("segno")
    if mk:
        out["market_key"] = str(mk)
    return out


def assert_no_forbidden_keys_in_row_v2(row: dict[str, Any]) -> list[str]:
    return [k for k in row if k in V35_V2_FORBIDDEN_INPUT_KEYS]


def build_market_input_context_v2(
    *,
    row: dict[str, Any],
    fair_info: dict[str, Any] | None,
    model_probs: dict[str, float | None] | None,
    market_key: str,
    fixture_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    clean = sanitize_kpi_row_v2(row)
    return _build_market_input_context_v1(
        row=clean,
        fair_info=fair_info,
        model_probs=model_probs,
        market_key=market_key,
        fixture_meta=fixture_meta,
    )


def evaluate_v35_v2_gate_from_inputs(
    *,
    execution_quote: float | None,
    execution_quote_real: bool,
    probability_cecchino: float | None,
    fair_book_probability: float | None,
    rating: float | None,
    pre_match_verified: bool = True,
) -> dict[str, Any]:
    """Gate V2 identico a V1, esposto per replay CSV senza fair_info objects."""
    reason_codes: list[str] = []
    if not pre_match_verified:
        return {
            "gate_status": "unavailable_inputs",
            "item_status": "not_calculable",
            "gate_reason_codes": ["invalid_pre_match_snapshot"],
            "expected_value": None,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    if not execution_quote_real:
        return {
            "gate_status": "unavailable_inputs",
            "item_status": "not_calculable",
            "gate_reason_codes": ["execution_quote_not_real"],
            "expected_value": None,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    eq = _safe_float(execution_quote)
    if eq is None or eq <= 1.0:
        return {
            "gate_status": "unavailable_inputs",
            "item_status": "not_calculable",
            "gate_reason_codes": ["invalid_execution_quote"],
            "expected_value": None,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    if probability_cecchino is None or not is_valid_open_probability(
        probability_cecchino
    ):
        return {
            "gate_status": "unavailable_inputs",
            "item_status": "not_calculable",
            "gate_reason_codes": ["missing_model_probability"],
            "expected_value": None,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    if fair_book_probability is None or not is_valid_open_probability(
        fair_book_probability
    ):
        return {
            "gate_status": "unavailable_inputs",
            "item_status": "not_calculable",
            "gate_reason_codes": ["missing_fair_book_probability"],
            "expected_value": None,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    if rating is None:
        return {
            "gate_status": "unavailable_inputs",
            "item_status": "not_calculable",
            "gate_reason_codes": ["rating_missing"],
            "expected_value": None,
            "rating": None,
            "rating_threshold": RATING_MIN_GATE,
        }
    p_cec = float(probability_cecchino)
    p_fair = float(fair_book_probability)
    ev = compute_expected_value(p_cec, eq)
    if ev <= 0:
        return {
            "gate_status": "gate_failed",
            "item_status": "gate_failed",
            "gate_reason_codes": ["non_positive_expected_value"],
            "expected_value": ev,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    if p_cec <= p_fair:
        return {
            "gate_status": "gate_failed",
            "item_status": "gate_failed",
            "gate_reason_codes": ["model_not_above_fair_book"],
            "expected_value": ev,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    if float(rating) < RATING_MIN_GATE:
        return {
            "gate_status": "gate_failed",
            "item_status": "gate_failed",
            "gate_reason_codes": ["rating_below_50"],
            "expected_value": ev,
            "rating": rating,
            "rating_threshold": RATING_MIN_GATE,
        }
    return {
        "gate_status": "passed",
        "item_status": "score",
        "gate_reason_codes": [],
        "expected_value": ev,
        "execution_quote": eq,
        "probability_cecchino": p_cec,
        "fair_book_probability": p_fair,
        "rating": float(rating),
        "rating_threshold": RATING_MIN_GATE,
    }


__all__ = [
    "assert_no_forbidden_keys_in_row_v2",
    "build_market_input_context_v2",
    "compute_expected_value",
    "evaluate_v35_gate",
    "evaluate_v35_v2_gate_from_inputs",
    "is_valid_open_probability",
    "resolve_execution_quote_v35",
    "resolve_probability_cecchino",
    "sanitize_kpi_row_v2",
    "verify_pre_match_snapshot",
]
