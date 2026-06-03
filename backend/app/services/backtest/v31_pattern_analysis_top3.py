"""Confronto top-3 strategie per fixture e cluster."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.backtest.v31_pattern_analysis_buckets import is_non_extreme_high_dynamic
from app.services.backtest.v31_pattern_analysis_recommendations import TOP3_KEYS

CLUSTER_PRIORITY = (
    "extreme_do_not_calibrate",
    "all_understate_high_non_extreme",
    "chaos_intercepts_outlier_only",
    "chaos_catches_high_non_extreme",
    "chaos_false_positive",
    "dynamic_guard_improves_bias",
    "dynamic_guard_worsens_bias",
    "all_three_close",
    "all_three_miss",
    "bias_corrected_best",
)


def _model_snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "predicted_total_sot": row.get("predicted_total_sot"),
        "abs_error": row.get("abs_error"),
        "win_quality": row.get("win_quality"),
        "diagnostic_weight": row.get("diagnostic_weight"),
        "predicted_bucket": row.get("predicted_bucket"),
    }


def _assign_cluster(
    *,
    actual_bucket_dynamic: str | None,
    models: dict[str, dict[str, Any] | None],
    is_outlier: bool,
) -> str:
    bias = models.get("v31_bias_corrected")
    hybrid = models.get("v31_bias_dynamic_high_guard")
    chaos = models.get("v31_chaos_game")
    if not bias or not hybrid or not chaos:
        return "bias_corrected_best"

    b_ae = float(bias.get("abs_error") or 999)
    h_ae = float(hybrid.get("abs_error") or 999)
    c_ae = float(chaos.get("abs_error") or 999)
    errors = [b_ae, h_ae, c_ae]

    if is_outlier:
        return "extreme_do_not_calibrate"

    all_under = all(
        m and m.get("win_quality") == "UNDERSTATED_WIN"
        for m in (bias, hybrid, chaos)
    )
    if all_under and is_non_extreme_high_dynamic(actual_bucket_dynamic):
        return "all_understate_high_non_extreme"

    if is_non_extreme_high_dynamic(actual_bucket_dynamic) and c_ae <= min(b_ae, h_ae) - 0.2:
        return "chaos_catches_high_non_extreme"

    if actual_bucket_dynamic == "extreme_total" and c_ae <= min(b_ae, h_ae) and c_ae > 2.5:
        return "chaos_intercepts_outlier_only"

    chaos_pred = float((chaos.get("predicted_total_sot") or 0))
    if chaos_pred >= 10 and actual_bucket_dynamic in ("low_total", "normal_total"):
        return "chaos_false_positive"

    if h_ae < b_ae - 0.3:
        return "dynamic_guard_improves_bias"
    if h_ae > b_ae + 0.3:
        return "dynamic_guard_worsens_bias"

    if all(e <= 1.5 for e in errors):
        return "all_three_close"
    if all(e > 2.5 for e in errors):
        return "all_three_miss"

    return "bias_corrected_best"


def build_top3_comparisons(
    rows_by_strategy: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Allinea fixture tra le 3 strategie."""
    bias_rows = rows_by_strategy.get("v31_bias_corrected") or []
    by_fid: dict[int, dict[str, dict[str, Any]]] = {}

    for key in TOP3_KEYS:
        for r in rows_by_strategy.get(key) or []:
            if r.get("prediction_status") != "ok":
                continue
            fid = int(r.get("fixture_id") or 0)
            by_fid.setdefault(fid, {})[key] = r

    fixtures: list[dict[str, Any]] = []
    cluster_counts: Counter[str] = Counter()

    for fid, model_rows in sorted(by_fid.items()):
        if len(model_rows) < 3:
            continue
        sample = model_rows["v31_bias_corrected"]
        actual = sample.get("actual_total_sot")
        dyn = sample.get("actual_bucket_dynamic")
        stat = sample.get("actual_bucket_static")
        is_outlier = bool(sample.get("is_extreme_outlier"))

        snapshots = {k: _model_snapshot(model_rows.get(k)) for k in TOP3_KEYS}
        errors = {
            k: float(snapshots[k]["abs_error"] or 999)
            for k in TOP3_KEYS
            if snapshots[k]
        }
        best = min(errors, key=errors.get) if errors else None

        cluster = _assign_cluster(
            actual_bucket_dynamic=dyn,
            models=snapshots,
            is_outlier=is_outlier,
        )
        cluster_counts[cluster] += 1

        b_ae = float((snapshots.get("v31_bias_corrected") or {}).get("abs_error") or 999)
        h_ae = float((snapshots.get("v31_bias_dynamic_high_guard") or {}).get("abs_error") or 999)
        c_ae = float((snapshots.get("v31_chaos_game") or {}).get("abs_error") or 999)

        fixtures.append(
            {
                "fixture_id": fid,
                "match": sample.get("match"),
                "actual_total_sot": actual,
                "actual_bucket_dynamic": dyn,
                "actual_bucket_static": stat,
                "models": snapshots,
                "best_model_on_fixture": best,
                "is_outlier": is_outlier,
                "dynamic_guard_improves_bias": h_ae < b_ae - 0.3,
                "dynamic_guard_worsens_bias": h_ae > b_ae + 0.3,
                "chaos_catches_high_non_extreme": (
                    is_non_extreme_high_dynamic(dyn) and c_ae <= min(b_ae, h_ae) - 0.2
                ),
                "chaos_chasing_outlier": (
                    dyn == "extreme_total" and c_ae <= min(b_ae, h_ae) and c_ae > 2.5
                ),
                "top3_cluster": cluster,
            },
        )

    total = len(fixtures) or 1
    summary = {
        "total_fixtures": len(fixtures),
        "counts": dict(cluster_counts),
        "pct": {k: round(100.0 * v / total, 1) for k, v in cluster_counts.items()},
        "cluster_order": list(CLUSTER_PRIORITY),
    }
    return fixtures, summary
