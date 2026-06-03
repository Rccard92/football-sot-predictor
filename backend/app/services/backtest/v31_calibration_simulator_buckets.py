"""Bucket SOT totali per metriche e classificazione."""

from __future__ import annotations

from typing import Any

BUCKET_KEYS = ("low_total", "normal_total", "high_total", "very_high_total")


def bucket_label(total: float | int | None) -> str | None:
    if total is None:
        return None
    t = float(total)
    if t <= 5:
        return "low_total"
    if t <= 9:
        return "normal_total"
    if t < 12:
        return "high_total"
    return "very_high_total"
