"""error_direction e suspicion_level per confronto componenti."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_component_actual_registry import ActualComparisonType


def match_error_type(match_error: float | None) -> str:
    if match_error is None:
        return "unknown"
    if match_error > 0.5:
        return "understated"
    if match_error < -0.5:
        return "overstated"
    return "aligned"


def compute_error_direction(
    *,
    match_error: float | None,
    predicted_value: float | None,
    actual_value: float | None,
    delta: float | None,
    comparison_type: ActualComparisonType,
) -> str:
    if comparison_type in ("diagnostic_only", "unavailable"):
        return "not_comparable"
    if match_error is None or predicted_value is None or actual_value is None:
        return "not_comparable"

    me = float(match_error)
    d = float(delta) if delta is not None else float(actual_value) - float(predicted_value)

    if abs(me) <= 1.5 and abs(d) < 0.3:
        return "aligned"

    if me > 0 and d > 0.3:
        return "underestimated"
    if me < 0 and d < -0.3:
        return "overestimated"

    if abs(d) < 0.3:
        return "aligned"
    return "not_comparable"


def compute_suspicion_level(
    *,
    error_direction: str,
    match_error: float | None,
    delta_pct: float | None,
) -> str:
    if error_direction in ("not_comparable", "aligned"):
        return "low"
    if match_error is None:
        return "low"
    me = abs(float(match_error))
    dp = abs(float(delta_pct)) if delta_pct is not None else 0.0
    if me >= 2.5 and dp >= 25 and error_direction in ("overestimated", "underestimated"):
        return "high"
    if me >= 1.5 and dp >= 15:
        return "medium"
    return "low"


def row_ui_status(error_direction: str, suspicion_level: str) -> str:
    if error_direction == "not_comparable":
        return "neutral"
    if error_direction == "aligned":
        return "aligned"
    if error_direction == "overestimated":
        return "overestimated"
    if error_direction == "underestimated":
        return "underestimated"
    if suspicion_level == "high":
        return "suspicious"
    return "neutral"
