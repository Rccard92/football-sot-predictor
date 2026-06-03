"""Test pattern verdict builder."""

from __future__ import annotations

from app.services.backtest.v31_pattern_analysis_verdict import build_pattern_verdict


def test_build_pattern_verdict():
    blocks = [
        {
            "key": "v31_bias_corrected",
            "high_total_non_extreme_summary": {"count_high_non_extreme": 47, "understated_count": 46},
            "extreme_outlier_summary": {"extreme_actual_count": 11},
        },
        {
            "key": "v31_bias_dynamic_high_guard",
            "high_total_non_extreme_summary": {"count_high_non_extreme": 47, "understated_count": 44},
            "hybrid_debug": {
                "boosted_fixtures_count": 156,
                "avg_boost_applied": 0.1436,
                "max_boost_applied": 0.75,
                "guardrail_blocked_count": 0,
            },
        },
        {
            "key": "v31_chaos_game",
            "high_total_non_extreme_summary": {"count_high_non_extreme": 47, "understated_count": 42},
            "high_and_outlier": {"predicted_high": 30, "predicted_very_high": 11},
            "losing_patterns": {
                "categories": {"BAD_LOSS_OVERESTIMATION": {"count": 43}},
                "special_categories": {"false_high_prediction": {"count": 14}},
            },
        },
    ]
    clusters = {
        "counts": {
            "dynamic_guard_improves_bias": 7,
            "dynamic_guard_worsens_bias": 24,
            "chaos_catches_high_non_extreme": 5,
            "chaos_false_positive": 14,
        },
    }
    dist = {"mean": 8.03, "p75": 10, "p90": 12, "p95": 13}
    verdict = build_pattern_verdict(blocks, clusters, dist)
    assert verdict["high_non_extreme"]["count"] == 47
    assert verdict["dynamic_guard"]["worsens"] == 24
    assert verdict["chaos"]["bad_loss_overestimation"] == 43
    assert verdict["extreme_count"] == 11
