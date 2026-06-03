"""Test Pattern Analysis v3.1."""

from __future__ import annotations

from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_strategies import predict_row
from app.services.backtest.v31_pattern_analysis_aggregators import winning_patterns
from app.services.backtest.v31_pattern_analysis_buckets import actual_bucket_dynamic, actual_bucket_static
from app.services.backtest.v31_pattern_analysis_distribution import compute_actual_sot_distribution
from app.services.backtest.v31_pattern_analysis_report import build_pattern_report_payload
from app.services.backtest.v31_pattern_analysis_top3 import build_top3_comparisons
from app.services.backtest.v31_pattern_analysis_win_quality import (
    classify_win_quality,
    diagnostic_weight_for,
    enrich_row_with_pattern_fields,
)
from tests.test_v31_calibration_simulator import _sample_row


def test_actual_sot_distribution_from_dataset():
    actuals = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    dist = compute_actual_sot_distribution(actuals)
    assert dist["count"] == 10
    assert dist["mean"] == 10.5
    assert dist["mean"] != 10.0  # non hardcoded
    assert dist["p95"] is not None
    assert dist["max"] == 15


def test_dynamic_bucket_extreme_at_p95():
    dist = compute_actual_sot_distribution([5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17])
    p25, p75, p90, p95 = dist["p25"], dist["p75"], dist["p90"], dist["p95"]
    assert p95 is not None
    assert actual_bucket_dynamic(p95 + 1, p25=p25, p75=p75, p90=p90, p95=p95) == "extreme_total"
    assert actual_bucket_static(16) == "extreme"


def test_win_quality_all_categories():
    cases = [
        (8.0, 9.0, 1.0, "normal_total", "HEALTHY_WIN"),
        (8.0, 10.0, 2.0, "high_total", "ACCEPTABLE_WIN"),
        (5.0, 9.0, 4.0, "high_total", "UNDERSTATED_WIN"),
        (6.0, 17.0, 11.0, "extreme_total", "EXTREME_WIN_OUTLIER"),
        (12.0, 8.0, 4.0, "normal_total", "BAD_LOSS_OVERESTIMATION"),
        (9.0, 8.0, 1.0, "normal_total", "CLOSE_LOSS"),
        (10.0, 8.0, 2.0, "normal_total", "NORMAL_LOSS"),
    ]
    for pred, act, ae, dyn, expected in cases:
        wq, win, loss = classify_win_quality(
            predicted=pred,
            actual=act,
            abs_error=ae,
            actual_bucket_dynamic=dyn,
        )
        assert wq == expected, (pred, act, expected, wq)
        assert diagnostic_weight_for(wq) > 0


def test_diagnostic_weights():
    assert diagnostic_weight_for("HEALTHY_WIN") == 1.0
    assert diagnostic_weight_for("EXTREME_WIN_OUTLIER") == 0.25
    assert diagnostic_weight_for("UNDERSTATED_WIN") == 0.9


def test_winning_patterns_includes_healthy_and_understated():
    rows = [
        {
            "prediction_status": "ok",
            "actual_total_sot": 9,
            "predicted_total_sot": 8,
            "abs_error": 1.0,
            "coverage_win": True,
            "coverage_loss": False,
            "win_quality": "HEALTHY_WIN",
            "actual_bucket_dynamic": "normal_total",
            "fixture_id": 1,
            "match": "A vs B",
        },
        {
            "prediction_status": "ok",
            "actual_total_sot": 12,
            "predicted_total_sot": 7,
            "abs_error": 5.0,
            "coverage_win": True,
            "coverage_loss": False,
            "win_quality": "UNDERSTATED_WIN",
            "actual_bucket_dynamic": "high_total",
            "fixture_id": 2,
            "match": "C vs D",
        },
    ]
    wp = winning_patterns(rows)
    assert wp["categories"]["HEALTHY_WIN"]["count"] == 1
    assert wp["categories"]["UNDERSTATED_WIN"]["count"] == 1


def test_top3_chaos_outlier_vs_high_non_extreme():
    base = {
        "prediction_status": "ok",
        "fixture_id": 101,
        "match": "X vs Y",
        "actual_total_sot": 11,
        "actual_bucket_dynamic": "high_total",
        "actual_bucket_static": "high",
        "is_extreme_outlier": False,
    }
    rows_by = {
        "v31_bias_corrected": [
            {**base, "predicted_total_sot": 7.5, "abs_error": 3.5, "win_quality": "UNDERSTATED_WIN", "diagnostic_weight": 0.9, "predicted_bucket": "normal_total"},
        ],
        "v31_bias_dynamic_high_guard": [
            {**base, "predicted_total_sot": 8.0, "abs_error": 3.0, "win_quality": "UNDERSTATED_WIN", "diagnostic_weight": 0.9, "predicted_bucket": "normal_total"},
        ],
        "v31_chaos_game": [
            {**base, "predicted_total_sot": 9.5, "abs_error": 1.5, "win_quality": "ACCEPTABLE_WIN", "diagnostic_weight": 0.6, "predicted_bucket": "high_total"},
        ],
    }
    fixtures, summary = build_top3_comparisons(rows_by)
    assert len(fixtures) == 1
    assert fixtures[0]["top3_cluster"] == "chaos_catches_high_non_extreme"
    assert fixtures[0]["chaos_catches_high_non_extreme"] is True

    outlier_base = {**base, "actual_total_sot": 17, "actual_bucket_dynamic": "extreme_total", "actual_bucket_static": "extreme", "is_extreme_outlier": True}
    rows_out = {
        "v31_bias_corrected": [{**outlier_base, "predicted_total_sot": 7.0, "abs_error": 10.0, "win_quality": "EXTREME_WIN_OUTLIER", "predicted_bucket": "normal_total"}],
        "v31_bias_dynamic_high_guard": [{**outlier_base, "predicted_total_sot": 7.5, "abs_error": 9.5, "win_quality": "EXTREME_WIN_OUTLIER", "predicted_bucket": "normal_total"}],
        "v31_chaos_game": [{**outlier_base, "predicted_total_sot": 9.0, "abs_error": 8.0, "win_quality": "EXTREME_WIN_OUTLIER", "predicted_bucket": "normal_total"}],
    }
    fixtures2, _ = build_top3_comparisons(rows_out)
    assert fixtures2[0]["top3_cluster"] == "extreme_do_not_calibrate"


def test_report_summary_strips_fixtures():
    raw = {
        "summary": {"fixtures_count": 10},
        "strategies": [
            {
                "key": "v31_bias_corrected",
                "winning_patterns": {
                    "categories": {"HEALTHY_WIN": {"count": 1, "examples": [{"fixture_id": 1}]}},
                },
            },
        ],
        "top3_fixtures": [{"fixture_id": 1}],
    }
    slim = build_pattern_report_payload(raw, detail="summary")
    assert "top3_fixtures" not in slim
    cat = slim["strategies"][0]["winning_patterns"]["categories"]["HEALTHY_WIN"]
    assert "examples" not in cat


def test_enrich_no_decision_field():
    row = predict_row(_sample_row(actual=10), "v31_bias_corrected")
    dist = compute_actual_sot_distribution([6, 7, 8, 9, 10, 11, 12])
    enriched = enrich_row_with_pattern_fields(
        row,
        p25=dist["p25"],
        p75=dist["p75"],
        p90=dist["p90"],
        p95=dist["p95"],
    )
    assert "decision" not in enriched
    assert enriched.get("win_quality") is not None
    assert "win_quality" not in (row.get("trace") or {})


def test_anti_leakage_win_quality_not_in_prediction_trace():
    row = _sample_row(actual=11)
    sig = extract_fixture_signals(row)
    assert sig is not None
    pred = predict_row(row, "v31_bias_corrected")
    trace = pred.get("trace") or {}
    assert "win_quality" not in trace
    assert "actual_bucket_dynamic" not in pred
    assert "diagnostic_weight" not in pred
