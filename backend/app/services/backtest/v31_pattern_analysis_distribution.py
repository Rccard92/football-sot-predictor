"""Distribuzione actual_total_sot sul dataset analizzato."""

from __future__ import annotations

import math
from typing import Any


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def compute_actual_sot_distribution(actuals: list[float | int]) -> dict[str, Any]:
    """Statistiche descrittive su actual_total_sot (solo post-match)."""
    vals = [float(v) for v in actuals if v is not None]
    if not vals:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "std": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p85": None,
            "p90": None,
            "p95": None,
            "p97": None,
            "max": None,
        }

    sorted_vals = sorted(vals)
    n = len(sorted_vals)
    mean = sum(sorted_vals) / n
    variance = sum((x - mean) ** 2 for x in sorted_vals) / n
    std = math.sqrt(variance)

    return {
        "count": n,
        "mean": round(mean, 4),
        "median": round(_percentile(sorted_vals, 0.50) or 0, 4),
        "std": round(std, 4),
        "p25": round(_percentile(sorted_vals, 0.25) or 0, 4),
        "p50": round(_percentile(sorted_vals, 0.50) or 0, 4),
        "p75": round(_percentile(sorted_vals, 0.75) or 0, 4),
        "p85": round(_percentile(sorted_vals, 0.85) or 0, 4),
        "p90": round(_percentile(sorted_vals, 0.90) or 0, 4),
        "p95": round(_percentile(sorted_vals, 0.95) or 0, 4),
        "p97": round(_percentile(sorted_vals, 0.97) or 0, 4),
        "max": round(max(sorted_vals), 4),
    }


def extract_actuals_from_rows(rows: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for r in rows:
        actual = r.get("actual_total_sot")
        if r.get("prediction_status") == "ok" and actual is not None:
            out.append(float(actual))
    return out
