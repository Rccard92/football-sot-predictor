"""Rollup copertura micro-variabili v2.1 per audit e data health."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.predictions_v21.v21_constants import QUALITY_MACRO_KEY


def _empty_bucket() -> dict[str, int]:
    return {
        "total": 0,
        "available": 0,
        "available_derived": 0,
        "missing": 0,
        "not_tracked_yet": 0,
        "fallback_partial": 0,
        "partial": 0,
        "fallback": 0,
        "fallback_historical_profiles": 0,
    }


def rollup_macro_micro_status(micros: list[dict[str, Any]]) -> dict[str, int]:
    bucket = _empty_bucket()
    for m in micros:
        if not isinstance(m, dict):
            continue
        status = str(m.get("status") or "missing")
        bucket["total"] += 1
        if status in bucket:
            bucket[status] += 1
        else:
            bucket["missing"] += 1
    return bucket


def build_v21_variable_coverage_from_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"by_macro": {}, "totals": _empty_bucket()}

    macroareas = raw.get("macroareas") if isinstance(raw.get("macroareas"), list) else []
    by_macro: dict[str, Any] = {}
    totals = Counter()
    for ma in macroareas:
        if not isinstance(ma, dict):
            continue
        key = str(ma.get("key") or "")
        if key == QUALITY_MACRO_KEY:
            continue
        micros = ma.get("micros") if isinstance(ma.get("micros"), list) else []
        bucket = rollup_macro_micro_status(micros)
        by_macro[key] = {
            "label": ma.get("label"),
            **bucket,
        }
        for k, v in bucket.items():
            totals[k] += v

    return {"by_macro": by_macro, "totals": dict(totals)}


def aggregate_v21_coverage_from_predictions(predictions_raw: list[dict[str, Any]]) -> dict[str, Any]:
    """Media rollup su più prediction raw_json (es. prossimo turno)."""
    if not predictions_raw:
        return {"by_macro": {}, "totals": _empty_bucket(), "predictions_sampled": 0}

    macro_acc: dict[str, Counter] = {}
    total_acc: Counter = Counter()
    for raw in predictions_raw:
        cov = build_v21_variable_coverage_from_raw(raw)
        for mk, bucket in cov.get("by_macro", {}).items():
            if mk not in macro_acc:
                macro_acc[mk] = Counter()
            for k, v in bucket.items():
                if k == "label":
                    continue
                macro_acc[mk][k] += int(v or 0)
        for k, v in cov.get("totals", {}).items():
            total_acc[k] += int(v or 0)

    n = len(predictions_raw)
    by_macro: dict[str, Any] = {}
    for mk, cnt in macro_acc.items():
        by_macro[mk] = {k: int(round(v / n)) for k, v in cnt.items()}

    return {
        "by_macro": by_macro,
        "totals": {k: int(round(v / n)) for k, v in total_acc.items()},
        "predictions_sampled": n,
        "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    }
