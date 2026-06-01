"""Test aggregator diagnostica Round Analysis (Step V3.0-A)."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_diagnostics_aggregator import (
    build_advice_diagnostic,
    build_critical_matches,
    build_diagnostics_payload,
    build_line_breakdown,
    build_sot_bucket_breakdown,
    compute_low_total_risk_score,
    diagnostics_actual_total_bucket,
    extract_v21_macro_averages,
    low_total_risk_bucket,
    macro_value_bucket,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _row(
    *,
    model_key: str = V11,
    actual: int = 8,
    predicted: float = 9.5,
    agg_advice: str = "GIOCA",
    agg_outcome: str = "WIN",
    caut_advice: str = "GIOCA",
    caut_outcome: str = "WIN",
    agg_line: float = 8.5,
    caut_line: float = 7.5,
    agg_edge: float = 1.0,
    caut_edge: float = 2.0,
    explanation_v21: dict | None = None,
    analysis_id: int = 1,
    fixture_id: int = 10,
) -> dict:
    return {
        "analysis_id": analysis_id,
        "round_number": 5,
        "fixture_id": fixture_id,
        "match": "A vs B",
        "actual_total_sot": actual,
        "model_key": model_key,
        "block": {
            "predicted_total_sot": predicted,
            "aggressive_advice": agg_advice,
            "aggressive_outcome": agg_outcome,
            "cautious_advice": caut_advice,
            "cautious_outcome": caut_outcome,
            "aggressive_line": agg_line,
            "cautious_line": caut_line,
            "aggressive_edge": agg_edge,
            "cautious_edge": caut_edge,
            "confidence": "medium",
            "sample_bucket": "medium_sample",
            "warnings": [],
        },
        "explanation_v21": explanation_v21,
    }


def test_diagnostics_actual_total_bucket_thresholds():
    assert diagnostics_actual_total_bucket(6) == "low_total"
    assert diagnostics_actual_total_bucket(7) == "medium_total"
    assert diagnostics_actual_total_bucket(9) == "medium_total"
    assert diagnostics_actual_total_bucket(10) == "high_total"


def test_macro_value_bucket():
    assert macro_value_bucket(0.85) == "low"
    assert macro_value_bucket(1.0) == "neutral"
    assert macro_value_bucket(1.15) == "high"


def test_extract_v21_macro_averages():
    expl = {
        "home": {
            "weighted_macro_multiplier": 1.02,
            "macros": [{"key": "offensive_production", "macro_index": 0.98, "status": "available"}],
        },
        "away": {
            "weighted_macro_multiplier": 1.04,
            "macros": [{"key": "offensive_production", "macro_index": 1.02, "status": "available"}],
        },
    }
    out = extract_v21_macro_averages(expl)
    assert out["offensive_production_avg"] == 1.0
    assert out["weighted_macro_multiplier_avg"] == 1.03


def test_sot_bucket_breakdown():
    rows = [
        _row(actual=5, predicted=8.0, caut_outcome="LOSS"),
        _row(actual=8, predicted=9.0, caut_outcome="WIN", fixture_id=11),
    ]
    out = build_sot_bucket_breakdown(rows)
    assert out["low_total"]["fixtures"] == 1
    assert out["medium_total"]["fixtures"] == 1
    assert out["medium_total"]["advised_cautious"]["wins"] == 1


def test_line_breakdown_calculated_all():
    rows = [_row(actual=10, predicted=10.0, agg_line=8.5, caut_line=7.5)]
    out = build_line_breakdown(rows)
    assert out["aggressive"]["8.5"]["calculated_all"]["wins"] == 1
    assert out["cautious"]["7.5"]["advised_only"]["wins"] == 1


def test_advice_diagnostic_avoided_and_missed():
    rows = [
        _row(caut_advice="NON GIOCARE", caut_outcome="LOSS"),
        _row(caut_advice="NON GIOCARE", caut_outcome="WIN", fixture_id=12),
    ]
    out = build_advice_diagnostic(rows)
    assert out["cautious"]["avoided_losses"] == 1
    assert out["cautious"]["missed_wins"] == 1


def test_low_total_risk_score_and_bucket():
    expl = {
        "home": {"macros": [{"key": "split", "macro_index": 0.9, "status": "partial_low_sample"}]},
        "away": {"macros": [{"key": "pace_control", "macro_index": 0.9, "status": "available"}]},
    }
    row = _row(
        model_key=V21,
        predicted=8.0,
        actual=5,
        explanation_v21=expl,
    )
    row["block"]["confidence"] = "low"
    row["block"]["sample_bucket"] = "early_low_sample"
    score = compute_low_total_risk_score(row)
    assert score >= 2.0
    assert low_total_risk_bucket(score) in ("medium", "high")


def test_critical_matches_categories():
    rows = [
        _row(model_key=V11, caut_outcome="WIN", fixture_id=1, analysis_id=1, predicted=10.0, actual=9),
        _row(model_key=V21, caut_outcome="LOSS", fixture_id=1, analysis_id=1, predicted=12.0, actual=9),
        _row(model_key=V11, caut_outcome="LOSS", fixture_id=2, analysis_id=1, predicted=8.0, actual=5),
        _row(model_key=V21, caut_outcome="LOSS", fixture_id=2, analysis_id=1, predicted=9.0, actual=5),
    ]
    critical = build_critical_matches(rows)
    cats = {c["category"] for c in critical}
    assert "v11_cautious_win_v21_cautious_loss" in cats
    assert "overestimate_v21" in cats


def test_build_diagnostics_payload_has_three_models():
    rows = [
        _row(model_key=V11),
        _row(model_key=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS, fixture_id=10),
    ]
    payload = build_diagnostics_payload(
        rows,
        [V11, V21],
        metadata={"analyzed_rounds": 1},
    )
    assert payload["report_type"] == "round_analysis_diagnostics_v30"
    assert V11 in payload["models"]
    assert "macro_buckets" in payload["v21_diagnostics"]
