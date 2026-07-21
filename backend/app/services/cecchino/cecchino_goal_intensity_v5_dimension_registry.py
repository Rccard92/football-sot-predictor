"""Registry canonico dimensioni Goal Intensity v5 — monitoring only."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

GOAL_INTENSITY_V5_DIMENSION_REGISTRY_VERSION = (
    "cecchino_goal_intensity_v5_dimension_registry_v1"
)

GOAL_INTENSITY_V5_DIMENSION_REGISTRY: dict[str, dict[str, Any]] = {
    "offensive_production": {
        "label_it": "Produzione offensiva",
        "metrics": {
            "long_term": "OP1_HOME_LONG_TERM",
            "recency": "OP2_HOME_RECENCY",
        },
    },
    "defensive_solidity": {
        "label_it": "Solidità difensiva",
        "metrics": {
            "vulnerability": "DV1_MEAN_CONCEDED",
            "weakest_defence": "DV2_WEAKEST_DEFENCE",
            "solidity_display": "defensive_solidity_display",
        },
    },
    "match_tempo": {
        "label_it": "Ritmo partita",
        "metrics": {
            "long_term": "MT1_LONG_TERM",
            "recency": "MT2_LONG_TERM_PLUS_RECENCY",
        },
    },
    "offensive_stability": {
        "label_it": "Stabilità offensiva",
        "metrics": {
            "volatility": "OV1_STD",
            "stability_display": "offensive_stability_display",
        },
    },
}

_METRIC_LABELS: dict[str, str] = {
    "long_term": "Lungo periodo",
    "recency": "Recency",
    "vulnerability": "Vulnerabilità media",
    "weakest_defence": "Difesa più debole",
    "solidity_display": "Solidità (display)",
    "volatility": "Volatilità",
    "stability_display": "Stabilità (display)",
}


def _is_valid_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if value is None:
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _percentile(sorted_vals: list[float], pct: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 6)
    k = (len(sorted_vals) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_vals[int(k)], 6)
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return round(d0 + d1, 6)


def extract_metric_values_from_snapshots(
    snapshots: list[Any],
    source_key: str,
) -> tuple[list[float], int, int]:
    """Returns (valid_values, missing_count, invalid_count)."""
    valid: list[float] = []
    missing = 0
    invalid = 0
    for snap in snapshots:
        ps = getattr(snap, "pillar_scores_payload", None) or {}
        if not isinstance(ps, dict):
            missing += 1
            continue
        raw = ps.get(source_key)
        if raw is None:
            missing += 1
            continue
        if not _is_valid_numeric(raw):
            invalid += 1
            continue
        valid.append(float(raw))
    return valid, missing, invalid


def compute_metric_stats(
    *,
    metric_key: str,
    source_key: str,
    snapshots: list[Any],
) -> dict[str, Any]:
    vals, missing, invalid = extract_metric_values_from_snapshots(snapshots, source_key)
    total = len(snapshots)
    n = len(vals)
    missing_share = round(missing / total, 6) if total else 0.0
    sorted_vals = sorted(vals)
    warning_codes: list[str] = []
    if invalid:
        warning_codes.append("invalid_numeric_values")
    if n == 0 and total > 0:
        warning_codes.append("no_valid_values")
    return {
        "key": metric_key,
        "source_key": source_key,
        "label": _METRIC_LABELS.get(metric_key, metric_key),
        "n": n,
        "missing": missing,
        "invalid": invalid,
        "missing_share": missing_share,
        "mean": round(sum(vals) / n, 6) if n else None,
        "median": round(median(vals), 6) if n else None,
        "min": round(min(vals), 6) if n else None,
        "max": round(max(vals), 6) if n else None,
        "p25": _percentile(sorted_vals, 0.25),
        "p75": _percentile(sorted_vals, 0.75),
        "warning_codes": warning_codes,
    }


def build_dimensions_from_snapshots(
    snapshots: list[Any],
) -> dict[str, Any]:
    dimensions: dict[str, Any] = {}
    snapshot_count = len(snapshots)
    for dim_key, spec in GOAL_INTENSITY_V5_DIMENSION_REGISTRY.items():
        metrics_out: list[dict[str, Any]] = []
        metrics_available = 0
        metrics_missing = 0
        dim_warnings: list[str] = []
        for mk, source_key in (spec.get("metrics") or {}).items():
            row = compute_metric_stats(
                metric_key=mk,
                source_key=str(source_key),
                snapshots=snapshots,
            )
            metrics_out.append(row)
            if row["n"] > 0:
                metrics_available += 1
            else:
                metrics_missing += 1
            dim_warnings.extend(row.get("warning_codes") or [])
        if metrics_available == 0 and snapshot_count > 0:
            data_quality_status = "missing"
        elif metrics_missing > 0:
            data_quality_status = "partial"
        else:
            data_quality_status = "ok"
        dimensions[dim_key] = {
            "key": dim_key,
            "label_it": spec.get("label_it", dim_key),
            "definition": "Dimensione distinta della struttura goal (research).",
            "snapshot_count": snapshot_count,
            "metrics_available": metrics_available,
            "metrics_missing": metrics_missing,
            "data_quality_status": data_quality_status,
            "warning_codes": list(dict.fromkeys(dim_warnings)),
            "metrics": metrics_out,
        }
    return dimensions
