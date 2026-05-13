"""Test manifest + trace builder (senza DB)."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import (
    build_applied_variable_trace_side,
    validate_model_trace,
)


def test_manifest_v04_countable_matches_trace_length():
    mv = BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
    specs = manifest_for_model(mv)
    n_count = len([s for s in specs if is_countable_role(s.application_role)])
    raw = {
        "offensive_production_component": {
            "value": 3.5,
            "weight_in_model": 0.30,
            "inputs": {
                "avg_sot_for": {"value": 4.0, "weight": 0.35, "contribution": 1.4},
                "avg_total_shots_for": {"value": 12.0, "weight": 0.2, "contribution": 2.4},
                "avg_inside_box_shots_for": {"value": 5.0, "weight": 0.15, "contribution": 0.75},
                "avg_outside_box_shots_for": {"value": 7.0, "weight": 0.1, "contribution": 0.7},
                "shot_accuracy_for": {"value": 0.3, "weight": 0.1, "contribution": 0.03},
                "avg_goals_for": {"value": 1.2, "weight": 0.05, "contribution": 0.06},
                "offensive_trend": {"value": 0.1, "weight": 0.05, "contribution": 0.005},
            },
            "fallbacks_used": [],
            "cap_applied": False,
        },
        "debug": {
            "baseline_other_inputs": {
                "opp_avg_sot_conceded": 3.2,
                "team_split_avg_sot_for": 3.3,
                "opp_split_avg_sot_conceded": 3.1,
                "team_last5_avg_sot_for": 3.4,
                "opp_last5_avg_sot_conceded": 3.0,
            },
        },
    }
    trace = build_applied_variable_trace_side(
        mv,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=24.0,
        prediction_confidence=72,
    )
    assert len(trace) == len(specs)
    assert len([r for r in trace if is_countable_role(str(r.get("application_role")))]) == n_count
    val = validate_model_trace(mv, raw, trace, stored_predicted_sot=3.37, sum_contributions=3.37)
    assert val.get("missing_trace_keys") == []
    assert val.get("extra_trace_keys") == []


def test_validate_detects_missing_trace_row():
    mv = BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
    trace: list = []
    val = validate_model_trace(mv, {}, trace, stored_predicted_sot=1.0, sum_contributions=1.0)
    assert val.get("missing_trace_keys")
