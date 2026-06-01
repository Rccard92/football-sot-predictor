"""Test simulatore calibrazione v3.0."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_calibration_simulator import (
    STRATEGY_IDS,
    apply_strategy,
    build_simulator_payload,
)
from app.services.backtest.round_analysis_low_total_risk_v2 import (
    compute_low_total_risk_v2_score,
    low_total_risk_v2_bucket,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _block(
    *,
    caut_advice: str = "GIOCA",
    caut_line: float = 6.5,
    caut_outcome: str = "WIN",
    predicted: float = 8.0,
    confidence: str = "medium",
    warnings: list[str] | None = None,
) -> dict:
    return {
        "predicted_total_sot": predicted,
        "cautious_advice": caut_advice,
        "cautious_line": caut_line,
        "cautious_outcome": caut_outcome,
        "confidence": confidence,
        "warnings": warnings or [],
    }


def _fx(
    *,
    actual: int = 9,
    v11: dict | None = None,
    v21: dict | None = None,
    macros: dict | None = None,
    split_status: str = "available",
    round_number: int = 10,
    fixture_id: int = 1,
) -> dict:
    entry = {
        "analysis_id": 1,
        "round_number": round_number,
        "fixture_id": fixture_id,
        "match": "A vs B",
        "actual_total_sot": actual,
        "models": {
            V11: v11 or _block(caut_line=6.5),
            V21: v21 or _block(caut_line=6.5),
        },
        "v21_macros": macros or {"weighted_macro_multiplier_avg": 1.0},
        "split_status": split_status,
        "explanation_v21": {},
    }
    score = compute_low_total_risk_v2_score(entry)
    entry["low_total_risk_v2_score"] = score
    entry["low_total_risk_v2_bucket"] = low_total_risk_v2_bucket(score)
    return entry


def test_v21_line_65_only():
    fixtures = [
        _fx(v21=_block(caut_line=6.5), fixture_id=1),
        _fx(v21=_block(caut_line=7.5), fixture_id=2),
    ]
    picks = apply_strategy("v2_1_cautious_line_6_5_only", fixtures)
    assert len(picks) == 1
    assert picks[0]["line"] == 6.5


def test_no_high_lines_excludes_85():
    fixtures = [_fx(v21=_block(caut_line=8.5), fixture_id=1)]
    picks = apply_strategy("v2_1_no_high_lines", fixtures)
    assert len(picks) == 0


def test_overheat_veto():
    fixtures = [
        _fx(
            v21=_block(caut_line=7.5, predicted=9.0),
            macros={"weighted_macro_multiplier_avg": 1.12},
            fixture_id=1,
        ),
    ]
    picks = apply_strategy("v2_1_overheat_veto", fixtures)
    assert len(picks) == 0


def test_consensus_min_line():
    fixtures = [
        _fx(
            v11=_block(caut_line=6.5),
            v21=_block(caut_line=7.5),
            actual=8,
            fixture_id=1,
        ),
    ]
    picks = apply_strategy("consensus_v11_v21_cautious_min_line", fixtures)
    assert len(picks) == 1
    assert picks[0]["line"] == 6.5
    assert picks[0]["outcome"] == "WIN"


def test_conservative_selector_v30():
    fixtures = [
        _fx(v21=_block(caut_line=6.5), fixture_id=1),
        _fx(
            v21=_block(caut_line=7.5, confidence="low"),
            macros={"weighted_macro_multiplier_avg": 1.0},
            fixture_id=2,
        ),
    ]
    picks = apply_strategy("conservative_selector_v30_candidate", fixtures)
    assert len(picks) == 1


def test_build_simulator_payload_ranking():
    fixtures = [
        _fx(round_number=8, fixture_id=i) for i in range(1, 15)
    ]
    payload = build_simulator_payload(fixtures, metadata={"analyzed_fixtures": len(fixtures)})
    assert payload["report_type"] == "round_analysis_calibration_simulator_v30"
    assert len(payload["strategies"]) == len(STRATEGY_IDS)
    assert len(STRATEGY_IDS) == 13
    assert "best_hit_rate" in payload["ranking"]
    assert "best_hit_rate_sufficient_volume" in payload["ranking"]
    assert payload["baselines"]["v2_1_cautious_advised"]["picks"] >= 0


def test_summarize_includes_v3_fields():
    fixtures = [_fx(actual=5, v21=_block(caut_line=6.5, predicted=8.0), fixture_id=1)]
    payload = build_simulator_payload(fixtures, metadata={})
    strat = payload["strategies"]["v2_1_cautious_advised"]
    assert "strategy_verdict" in strat
    assert "loss_diagnostics" in strat
    assert "by_low_total_risk_v2" in strat
    assert "walk_forward_stability" in strat
    if strat["summary"]["losses"] > 0:
        assert len(strat["loss_diagnostics"]) == strat["summary"]["losses"]


def test_walk_forward_segments():
    fixtures = [
        _fx(round_number=10, fixture_id=1),
        _fx(round_number=20, fixture_id=2),
        _fx(round_number=30, fixture_id=3),
    ]
    payload = build_simulator_payload(fixtures, metadata={})
    strat = payload["strategies"]["v2_1_cautious_advised"]
    assert "rounds_5_15" in strat["walk_forward"]
    assert strat["walk_forward"]["rounds_5_15"]["picks"] == 1
