"""Test strategie value selector v3.0-C."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_calibration_simulator import apply_strategy
from app.services.backtest.round_analysis_low_total_risk_v2 import (
    compute_low_total_risk_v2_score,
    low_total_risk_v2_bucket,
)
from app.services.backtest.round_analysis_value_selector_helpers import compute_strategy_verdict
from app.services.backtest.round_analysis_value_selector_strategies import (
    V3_STRATEGY_IDS,
    reset_hybrid_audit,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _block(
    *,
    caut_line: float = 6.5,
    predicted: float = 7.8,
    confidence: str = "medium",
    warnings: list[str] | None = None,
    sample_bucket: str | None = None,
) -> dict:
    return {
        "predicted_total_sot": predicted,
        "cautious_advice": "GIOCA",
        "cautious_line": caut_line,
        "confidence": confidence,
        "warnings": warnings or [],
        "sample_bucket": sample_bucket,
    }


def _fx(
    *,
    actual: int = 9,
    v11: dict | None = None,
    v21: dict | None = None,
    macros: dict | None = None,
    split_status: str = "available",
    fixture_id: int = 1,
) -> dict:
    entry = {
        "analysis_id": 1,
        "round_number": 10,
        "fixture_id": fixture_id,
        "match": "A vs B",
        "actual_total_sot": actual,
        "models": {
            V11: v11 or _block(predicted=7.6),
            V21: v21 or _block(predicted=7.8),
        },
        "v21_macros": macros
        or {
            "weighted_macro_multiplier_avg": 1.0,
            "chance_quality_avg": 1.0,
            "pace_control_avg": 1.0,
            "injuries_unavailable_avg": 0.95,
            "lineups_avg": 0.98,
            "player_layer_avg": 1.05,
        },
        "split_status": split_status,
        "explanation_v21": {},
    }
    score = compute_low_total_risk_v2_score(entry)
    entry["low_total_risk_v2_score"] = score
    entry["low_total_risk_v2_bucket"] = low_total_risk_v2_bucket(score)
    return entry


def test_v3_safe_65_strict_filters_pred_range():
    ok = _fx(v21=_block(caut_line=6.5, predicted=7.8))
    low = _fx(v21=_block(caut_line=6.5, predicted=7.2), fixture_id=2)
    picks = apply_strategy("v3_safe_6_5_strict", [ok, low])
    assert len(picks) == 1
    assert picks[0]["strategy_id"] == "v3_safe_6_5_strict"


def test_v3_consensus_min_line_uses_min():
    fx = _fx(
        v11=_block(caut_line=6.5, predicted=7.5),
        v21=_block(caut_line=7.5, predicted=8.4),
        fixture_id=1,
    )
    picks = apply_strategy("v3_consensus_balanced_min_line", [fx])
    assert len(picks) == 1
    assert picks[0]["line"] == 6.5


def test_v3_hybrid_tier_and_reason_codes():
    reset_hybrid_audit()
    fx = _fx(
        v11=_block(caut_line=6.5, predicted=7.5),
        v21=_block(caut_line=6.5, predicted=7.8),
        fixture_id=1,
    )
    picks = apply_strategy("v3_hybrid_value_selector", [fx])
    assert len(picks) == 1
    assert picks[0]["confidence_tier"] == "strong"
    assert "consensus_strong" in picks[0]["reason_codes"]


def test_v3_hybrid_excludes_high_risk_v2():
    reset_hybrid_audit()
    fx = _fx(
        v21=_block(caut_line=6.5, predicted=7.8, confidence="low", warnings=["a", "b", "c", "d"]),
        macros={
            "weighted_macro_multiplier_avg": 1.20,
            "chance_quality_avg": 1.20,
            "pace_control_avg": 1.15,
            "injuries_unavailable_avg": 0.80,
            "lineups_avg": 0.90,
            "player_layer_avg": 0.95,
        },
        split_status="missing",
        fixture_id=1,
    )
    picks = apply_strategy("v3_hybrid_value_selector", [fx])
    assert len(picks) == 0


def test_strategy_verdict_thresholds():
    assert compute_strategy_verdict(80, 72.0) == "excellent"
    assert compute_strategy_verdict(60, 70.0) == "promising"
    assert compute_strategy_verdict(50, 73.0) == "too_selective"
    assert compute_strategy_verdict(100, 65.0) == "weak"


def test_v3_strategy_ids_count():
    assert len(V3_STRATEGY_IDS) == 5
