"""Test unit simulatore predittivo v3.1."""

from __future__ import annotations

from app.services.backtest.v31_calibration_simulator_base_sot import (
    absolute_from_field,
    calculate_team_base_sot,
)
from app.services.backtest.v31_calibration_simulator_buckets import bucket_label
from app.services.backtest.v31_calibration_simulator_cohort import build_cohort_from_rows
from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_metrics import (
    bucket_metrics,
    compute_best_by,
    prediction_distribution,
    predictive_metrics,
    prediction_diagnostics,
    regression_metrics,
    walk_forward_metrics,
)
from app.services.backtest.v31_calibration_team_raw_resolver import resolve_shots_for_side
from app.services.backtest.v31_calibration_simulator_strategies import (
    STRATEGY_KEYS,
    predict_row,
    predict_rows_for_strategy,
)


def _macro_side(off: float = 1.05) -> dict:
    return {
        "offensive_production_index": off,
        "opponent_defensive_resistance_index": 1.0,
        "recent_form_index": 1.02,
        "chance_quality_index": 1.03,
        "pace_control_index": 1.0,
        "home_away_split_index": 1.01,
        "player_layer_index": 1.0,
        "injuries_unavailable_index": 0.98,
        "lineups_index": 1.0,
        "weighted_macro_multiplier": 1.0,
    }


def _sample_row(
    *,
    round_number: int = 10,
    actual: int = 9,
    avg_sot_for: float = 1.05,
    use_absolute_sot: bool = False,
) -> dict:
    if use_absolute_sot:
        home_team = {
            "avg_sot_for": 3.5,
            "avg_sot_against": 3.2,
            "last5_avg_sot_for": 3.4,
            "home_away_split_sot_for": 3.6,
            "avg_xg_for": 1.3,
            "avg_total_shots_for": 12.0,
        }
        away_team = {
            "avg_sot_for": 3.2,
            "avg_sot_against": 3.5,
            "last5_avg_sot_for": 3.1,
            "home_away_split_sot_for": 3.0,
            "avg_xg_for": 1.2,
            "avg_total_shots_for": 11.0,
        }
    else:
        home_team = {
            "avg_sot_for": avg_sot_for,
            "avg_sot_against": 1.0,
            "last5_avg_sot_for": avg_sot_for,
            "home_away_split_sot_for": avg_sot_for,
            "avg_xg_for": 1.03,
        }
        away_team = {
            "avg_sot_for": avg_sot_for - 0.02,
            "avg_sot_against": 1.0,
            "last5_avg_sot_for": avg_sot_for,
            "home_away_split_sot_for": avg_sot_for,
            "avg_xg_for": 1.02,
        }

    return {
        "metadata": {
            "fixture_id": 100 + round_number,
            "round_number": round_number,
            "home_team_name": "Alpha",
            "away_team_name": "Beta",
        },
        "target": {
            "actual_total_sot": actual,
            "actual_home_sot": 5,
            "actual_away_sot": 4,
        },
        "features": {
            "team_raw_features": {"home": home_team, "away": away_team},
            "existing_macro_features": {
                "home": _macro_side(),
                "away": _macro_side(1.04),
            },
            "player_layer": {
                "home": {"player_layer_index_existing": 1.0, "starting_xi_available": True},
                "away": {"player_layer_index_existing": 1.0, "starting_xi_available": True},
            },
            "lineups": {
                "home": {"lineup_available": True},
                "away": {"lineup_available": True},
            },
            "unavailable": {"home": {}, "away": {}},
            "data_quality": {
                "team_stats_status": "ok",
                "warning_count": 0,
                "fallback_count": 0,
                "lineup_status": "ok",
                "player_layer_status": "ok",
                "unavailable_status": "ok",
            },
            "league_context": {"round_number": round_number},
        },
        "comparisons": {
            "v2_1_predicted_total": 8.0,
            "allowed_for_v31_training": False,
        },
    }


def test_absolute_from_field_macro_index():
    missing: list[str] = []
    v = absolute_from_field(1.05, 3.35, "test", missing)
    assert v is not None
    assert 3.0 < v < 4.0
    assert not missing


def test_calculate_team_base_sot_realistic():
    side = {
        "avg_sot_for": 3.5,
        "last5_avg_sot_for": 3.4,
        "home_away_split_sot_for": 3.6,
        "avg_xg_for": 1.3,
        "avg_total_shots_for": 12.0,
    }
    opp = {"avg_sot_against": 3.2}
    base, _trace = calculate_team_base_sot(side, opp, {})
    assert base is not None
    assert 2.5 <= base <= 6.5


def test_predict_row_realistic_total_from_macro_indices():
    row = _sample_row()
    out = predict_row(row, "v31_context_adjusted")
    assert out["prediction_status"] == "ok"
    total = float(out["predicted_total_sot"])
    assert 5.0 <= total <= 11.0
    assert "decision" not in out


def test_macro_index_and_absolute_similar_scale():
    r_idx = _sample_row(avg_sot_for=1.05, use_absolute_sot=False)
    r_abs = _sample_row(use_absolute_sot=True)
    t_idx = float(predict_row(r_idx, "v31_context_adjusted")["predicted_total_sot"])
    t_abs = float(predict_row(r_abs, "v31_context_adjusted")["predicted_total_sot"])
    assert abs(t_idx - t_abs) < 2.5


def test_all_fixtures_predicted_ok():
    rows = [_sample_row(round_number=r, actual=8 + (r % 3)) for r in range(5, 20)]
    for key in STRATEGY_KEYS:
        simulated = predict_rows_for_strategy(rows, key)
        assert len(simulated) == len(rows)
        ok = sum(1 for s in simulated if s["prediction_status"] == "ok")
        assert ok == len(rows), key


def test_coverage_win_rule():
    row = _sample_row(actual=10)
    out = predict_row(row, "v31_equal_weights")
    assert out["prediction_status"] == "ok"
    pred = float(out["predicted_total_sot"])
    if 10 > pred:
        assert out["coverage_outcome"] == "win"
    else:
        assert out["coverage_outcome"] == "loss"


def test_prediction_diagnostics_no_scale_warning_on_normal_batch():
    rows = [predict_row(_sample_row(round_number=r), "v31_equal_weights") for r in range(5, 20)]
    diag = prediction_diagnostics(rows)
    assert diag["predicted_total_avg"] is not None
    assert 6.5 <= diag["predicted_total_avg"] <= 9.5
    assert diag["scale_warning"] is False


def test_compute_best_by_recommends_with_predictions_ok():
    blocks = [
        {
            "key": "a",
            "predictive_metrics": {
                "predictions_ok": 15,
                "mae": 3.0,
                "rmse": 3.5,
                "bias": -1.0,
                "within_1_5_pct": 30.0,
                "coverage_win_rate": 80.0,
            },
            "bucket_metrics": {"high_total_recall": 20.0},
            "prediction_distribution": {"compression_ratio": 0.4, "model_too_flat": True},
        },
        {
            "key": "b",
            "predictive_metrics": {
                "predictions_ok": 15,
                "mae": 2.0,
                "rmse": 2.5,
                "bias": -0.3,
                "within_1_5_pct": 50.0,
                "coverage_win_rate": 55.0,
            },
            "bucket_metrics": {"high_total_recall": 45.0},
            "prediction_distribution": {"compression_ratio": 0.75, "model_too_flat": False},
        },
    ]
    best = compute_best_by(blocks, fixtures_total=15)
    assert best["recommended_strategy"] is not None
    assert best["recommended_strategy"] in ("a", "b")
    assert "hit_rate" not in best


def test_regression_mae_not_extreme_bias():
    rows = [predict_row(_sample_row(round_number=r), "v31_equal_weights") for r in range(5, 18)]
    reg = regression_metrics(rows)
    assert reg["bias"] is not None
    assert abs(float(reg["bias"])) < 4.0


def test_predictive_metrics_within_bands():
    rows = [predict_row(_sample_row(round_number=r), "v31_equal_weights") for r in range(5, 18)]
    pm = predictive_metrics(rows)
    assert pm["fixtures_total"] == len(rows)
    assert pm["predictions_ok"] == len(rows)
    assert pm["within_1_5_pct"] is not None


def test_walk_forward_splits_numeric_only():
    rows = []
    for r in range(5, 38):
        rows.append(predict_row(_sample_row(round_number=r), "v31_equal_weights"))
    wf = walk_forward_metrics(rows)
    split = wf["wf_5_15_to_16_26"]
    assert split["test_fixture_count"] > 0
    assert "test_predictive" in split
    assert "test_betting" not in split


def test_all_strategy_keys_predict():
    row = _sample_row()
    for key in STRATEGY_KEYS:
        out = predict_row(row, key)
        assert out is not None
        assert out["prediction_status"] == "ok"


def test_invalid_features_failed_not_skipped():
    row = _sample_row()
    row["features"] = None
    out = predict_row(row, "v31_equal_weights")
    assert out["prediction_status"] == "failed"
    assert out["error_code"] == "V31_INVALID_FEATURES"


def test_shots_resolved_from_pace_macro():
    row = _sample_row()
    sig = extract_fixture_signals(row)
    assert sig is not None
    res = resolve_shots_for_side(sig.home.team_raw, sig.home.macros, sig.league_context)
    assert res["resolved"] is True
    out = predict_row(row, "v31_core_sot_xg")
    trace = out.get("trace") or {}
    home_trace = trace.get("home_base_trace") or {}
    comps = home_trace.get("components") or {}
    assert comps.get("shots_to_sot") is not None


def test_predicted_buckets_on_rows():
    row = _sample_row(actual=11)
    out = predict_row(row, "v31_equal_weights")
    assert out.get("predicted_bucket") is not None
    assert out.get("actual_bucket") == bucket_label(11)


def test_bucket_metrics_structure():
    rows = [predict_row(_sample_row(round_number=r, actual=8 + (r % 4)), "v31_equal_weights") for r in range(5, 25)]
    bm = bucket_metrics(rows)
    assert bm.get("bucket_accuracy") is not None
    assert "confusion_matrix" in bm


def test_prediction_distribution_compression():
    rows = [
        predict_row(_sample_row(round_number=r, actual=5 + (r % 6)), "v31_low_variance")
        for r in range(5, 25)
    ]
    dist = prediction_distribution(rows)
    assert dist.get("predicted_std") is not None
    assert dist.get("compression_ratio") is not None


def _extreme_cohort_rows(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    for i, r in enumerate(range(5, 5 + n)):
        if i % 2 == 0:
            row = _sample_row(round_number=r, actual=4, avg_sot_for=0.62)
            low = {
                **_macro_side(0.62),
                "pace_control_index": 0.62,
                "offensive_production_index": 0.62,
                "chance_quality_index": 0.62,
            }
            row["features"]["existing_macro_features"]["home"] = low
            row["features"]["existing_macro_features"]["away"] = low
        else:
            row = _sample_row(round_number=r, actual=12, avg_sot_for=1.35)
            hi = {**_macro_side(1.35), "pace_control_index": 1.35, "offensive_production_index": 1.35}
            row["features"]["existing_macro_features"]["home"] = hi
            row["features"]["existing_macro_features"]["away"] = hi
            row["features"]["team_raw_features"]["home"]["avg_total_shots_for"] = 15.0
            row["features"]["team_raw_features"]["away"]["avg_total_shots_for"] = 14.5
        rows.append(row)
    return rows


def test_variance_unlocked_wider_range():
    rows = _extreme_cohort_rows()
    cohort = build_cohort_from_rows(rows)
    preds = [
        float(predict_row(r, "v31_variance_unlocked", cohort=cohort)["predicted_total_sot"])
        for r in rows
    ]
    assert max(preds) > 10.0
    assert min(preds) < max(preds) - 2.5


def test_strategy_count_includes_aggressive():
    assert len(STRATEGY_KEYS) >= 14
    assert "v31_variance_unlocked" in STRATEGY_KEYS
    assert "v31_big_match_boost" in STRATEGY_KEYS


def test_probable_reason_none_boost_reason():
    from app.services.backtest.v31_calibration_simulator_error_reasons import (
        probable_reason,
        safe_probable_reason,
    )

    row = {
        "predicted_total_sot": 10.0,
        "actual_total_sot": 6.0,
        "error": 4.0,
        "predicted_bucket": "high_total",
        "actual_bucket": "normal_total",
        "trace": {"boost_reason": None, "boost_applied": None},
    }
    assert isinstance(probable_reason(row), str)
    assert isinstance(safe_probable_reason(row), str)


def test_normalize_prediction_trace_defaults():
    from app.services.backtest.v31_calibration_simulator_trace import normalize_prediction_trace

    t = normalize_prediction_trace({"boost_reason": None, "boost_applied": None})
    assert t["boost_reason"] == ""
    assert t["boost_applied"] == 0.0
    assert t["league_blend_applied"] == 0.0
    assert t["interaction_scores"] == {}


def test_error_distribution_incomplete_trace():
    from app.services.backtest.v31_calibration_simulator_metrics import error_distribution

    row = predict_row(_sample_row(actual=12), "v31_equal_weights")
    row["trace"] = {"boost_reason": None, "boost_applied": None}
    row["error"] = float(row["predicted_total_sot"]) - 12.0
    dist = error_distribution([row])
    worst = dist.get("worst_overestimations") or dist.get("worst_underestimations") or []
    if worst:
        assert worst[0].get("probable_reason")
    else:
        assert dist.get("overestimated_count", 0) >= 0
