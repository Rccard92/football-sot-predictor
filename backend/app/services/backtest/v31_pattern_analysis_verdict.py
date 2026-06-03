"""Verdetto consolidato Pattern Analysis per UI."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_pattern_analysis_recommendations import TOP3_KEYS


def build_pattern_verdict(
    strategy_blocks: list[dict[str, Any]],
    top3_cluster_summary: dict[str, Any],
    distribution: dict[str, Any],
) -> dict[str, Any]:
    by_key = {b["key"]: b for b in strategy_blocks}
    clusters = top3_cluster_summary.get("counts") or {}

    high_ne: dict[str, dict[str, int]] = {}
    for key in TOP3_KEYS:
        hne = by_key.get(key, {}).get("high_total_non_extreme_summary") or {}
        high_ne[key] = {
            "count": int(hne.get("count_high_non_extreme") or 0),
            "understated": int(hne.get("understated_count") or 0),
        }

    bias_hne = high_ne.get("v31_bias_corrected", {})
    main_issue = "models_understate_high_non_extreme"
    if bias_hne.get("count", 0) > 0 and bias_hne.get("understated", 0) / max(bias_hne["count"], 1) >= 0.4:
        main_issue = "models_understate_high_non_extreme"

    hybrid = by_key.get("v31_bias_dynamic_high_guard", {})
    chaos = by_key.get("v31_chaos_game", {})
    hd = hybrid.get("hybrid_debug") or {}
    h_chaos = chaos.get("high_and_outlier") or {}
    lp_chaos = chaos.get("losing_patterns") or {}

    return {
        "main_issue": main_issue,
        "high_non_extreme": {
            "count": bias_hne.get("count", 0),
            "understated_by_model": {k: v["understated"] for k, v in high_ne.items()},
            "total_by_model": {k: v["count"] for k, v in high_ne.items()},
        },
        "extreme_count": int(
            (by_key.get("v31_bias_corrected", {}).get("extreme_outlier_summary") or {}).get(
                "extreme_actual_count",
            )
            or 0,
        ),
        "dynamic_guard": {
            "boosted_fixtures_count": hd.get("boosted_fixtures_count"),
            "avg_boost_applied": hd.get("avg_boost_applied"),
            "max_boost_applied": hd.get("max_boost_applied"),
            "guardrail_blocked_count": hd.get("guardrail_blocked_count"),
            "improves": int(clusters.get("dynamic_guard_improves_bias") or 0),
            "worsens": int(clusters.get("dynamic_guard_worsens_bias") or 0),
        },
        "chaos": {
            "predicted_high": int(h_chaos.get("predicted_high") or 0)
            + int(h_chaos.get("predicted_very_high") or 0),
            "catches_high_non_extreme": int(clusters.get("chaos_catches_high_non_extreme") or 0),
            "false_positive": int(clusters.get("chaos_false_positive") or 0)
            or int((lp_chaos.get("special_categories") or {}).get("false_high_prediction", {}).get("count") or 0),
            "bad_loss_overestimation": int(
                ((lp_chaos.get("categories") or {}).get("BAD_LOSS_OVERESTIMATION") or {}).get("count") or 0,
            ),
        },
        "distribution_snapshot": {
            "mean": distribution.get("mean"),
            "p75": distribution.get("p75"),
            "p90": distribution.get("p90"),
            "p95": distribution.get("p95"),
        },
    }
