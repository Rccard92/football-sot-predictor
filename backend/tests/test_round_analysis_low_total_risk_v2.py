"""Test low_total_risk_v2 (simulatore v3.0-C)."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_low_total_risk_v2 import (
    compute_low_total_risk_v2_score,
    low_total_risk_v2_bucket,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _fx(**kwargs) -> dict:
    base = {
        "models": {
            V11: {"predicted_total_sot": 7.5},
            V21: {"predicted_total_sot": 8.0, "confidence": "medium", "warnings": []},
        },
        "v21_macros": {},
        "split_status": "available",
    }
    base.update(kwargs)
    return base


def test_low_bucket_minimal_risk():
    score = compute_low_total_risk_v2_score(_fx())
    assert score == 0
    assert low_total_risk_v2_bucket(score) == "low"


def test_high_bucket_overheat_and_gap():
    fx = _fx(
        models={
            V11: {"predicted_total_sot": 7.0},
            V21: {
                "predicted_total_sot": 8.5,
                "confidence": "low",
                "warnings": ["a", "b", "c", "d"],
            },
        },
        v21_macros={
            "weighted_macro_multiplier_avg": 1.20,
            "chance_quality_avg": 1.20,
            "pace_control_avg": 1.15,
            "injuries_unavailable_avg": 0.80,
            "lineups_avg": 0.90,
            "player_layer_avg": 0.95,
        },
        split_status="missing",
    )
    score = compute_low_total_risk_v2_score(fx)
    assert score >= 4
    assert low_total_risk_v2_bucket(score) == "high"


def test_medium_bucket():
    fx = _fx(
        models={
            V11: {"predicted_total_sot": 7.5},
            V21: {
                "predicted_total_sot": 8.0,
                "confidence": "low",
                "warnings": ["w1", "w2", "w3", "w4"],
            },
        },
        split_status="partial_low_sample",
    )
    score = compute_low_total_risk_v2_score(fx)
    assert 2 <= score <= 3
    assert low_total_risk_v2_bucket(score) == "medium"
