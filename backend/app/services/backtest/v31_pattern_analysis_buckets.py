"""Bucket dinamici (percentili dataset) e statici (UI)."""

from __future__ import annotations

from typing import Any

DYNAMIC_BUCKET_KEYS = (
    "low_total",
    "normal_total",
    "high_total",
    "very_high_total",
    "extreme_total",
)

STATIC_BUCKET_KEYS = (
    "low",
    "normal",
    "high",
    "very_high",
    "extreme",
)


def dynamic_bucket_thresholds(distribution: dict[str, Any]) -> dict[str, float | None]:
    return {
        "p25": distribution.get("p25"),
        "p75": distribution.get("p75"),
        "p90": distribution.get("p90"),
        "p95": distribution.get("p95"),
    }


def actual_bucket_dynamic(
    actual: float | int | None,
    *,
    p25: float | None,
    p75: float | None,
    p90: float | None,
    p95: float | None,
) -> str | None:
    if actual is None or p25 is None or p75 is None or p90 is None or p95 is None:
        return None
    t = float(actual)
    if t <= p25:
        return "low_total"
    if t <= p75:
        return "normal_total"
    if t <= p90:
        return "high_total"
    if t <= p95:
        return "very_high_total"
    return "extreme_total"


def actual_bucket_static(actual: float | int | None) -> str | None:
    if actual is None:
        return None
    t = float(actual)
    if t <= 5:
        return "low"
    if t <= 9:
        return "normal"
    if t <= 12:
        return "high"
    if t <= 14:
        return "very_high"
    return "extreme"


def is_high_or_above_dynamic(bucket: str | None) -> bool:
    return bucket in ("high_total", "very_high_total", "extreme_total")


def is_non_extreme_high_dynamic(bucket: str | None) -> bool:
    return bucket in ("high_total", "very_high_total")
