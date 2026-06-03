"""Test context builder analisi AI mirata."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.backtest.predictive_ai_context_builders import (
    _build_false_high_predictions,
    _build_missed_high_non_extreme,
)


def _mock_prediction(**kwargs):
    row = MagicMock()
    defaults = {
        "fixture_id": 1,
        "round_number": 10,
        "home_team_name": "A",
        "away_team_name": "B",
        "strategy_key": "v31_bias_corrected",
        "predicted_total_sot": 8.0,
        "actual_total_sot": 11.0,
        "error": -3.0,
        "abs_error": 3.0,
        "predicted_bucket": "normal_total",
        "actual_bucket": "high",
        "actual_bucket_dynamic": "high_total",
        "win_quality": "UNDERSTATED_WIN",
        "outcome_type": "high_missed",
        "reason_codes_json": [{"code": "HIGH_TOTAL_MISSED"}],
        "probable_reason": "test",
        "boost_applied": 0.1,
        "high_total_signal": 55.0,
        "feature_snapshot_json": {},
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def test_missed_high_filters_non_extreme():
    db = MagicMock()
    run = MagicMock()
    run.id = 1
    run.pattern_payload_json = {
        "summary": {
            "actual_sot_distribution": {"p75": 10.0},
            "dynamic_bucket_thresholds": {"p75": 10.0, "p90": 11.0, "p95": 12.0},
        },
    }

    rows = [
        _mock_prediction(fixture_id=1, strategy_key="v31_bias_corrected", actual_bucket_dynamic="high_total"),
        _mock_prediction(fixture_id=1, strategy_key="v31_bias_dynamic_high_guard", predicted_total_sot=8.5),
        _mock_prediction(fixture_id=1, strategy_key="v31_chaos_game", predicted_total_sot=9.0),
        _mock_prediction(
            fixture_id=2,
            strategy_key="v31_bias_corrected",
            actual_bucket_dynamic="extreme_total",
            actual_total_sot=16.0,
        ),
    ]
    db.scalars.return_value.all.return_value = rows

    ctx = _build_missed_high_non_extreme(db, run)
    assert ctx["analysis_type"] == "missed_high_non_extreme"
    assert len(ctx["top_fixtures"]) == 1
    assert ctx["top_fixtures"][0]["fixture_id"] == 1


def test_false_high_filters_threshold():
    db = MagicMock()
    run = MagicMock()
    run.id = 1
    run.pattern_payload_json = {"summary": {}}

    rows = [
        _mock_prediction(
            strategy_key="v31_chaos_game",
            predicted_total_sot=10.0,
            actual_total_sot=6.0,
            abs_error=4.0,
        ),
    ]
    db.scalars.return_value.all.return_value = rows

    ctx = _build_false_high_predictions(db, run)
    assert ctx["aggregates"]["total_false_high_rows"] == 1
    assert ctx["top_examples"][0]["strategy_key"] == "v31_chaos_game"
