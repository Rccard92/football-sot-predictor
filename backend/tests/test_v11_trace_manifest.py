"""Manifest e trace baseline_v1_1_sot."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side


def test_v11_manifest_one_formula_nine_inputs():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    formula_direct = [s for s in specs if s.application_role == "direct_formula_component"]
    comp_in = [s for s in specs if s.application_role == "component_input"]
    assert len(formula_direct) == 1
    assert formula_direct[0].trace_key == "v11_term_offensive_production_component"
    assert len(comp_in) == 9
    assert all(s.parent_component == "offensive_production_component" for s in comp_in)


def test_v11_trace_from_saved_raw():
    raw = {
        "prediction_valid": True,
        "formula_quality_status": "ok",
        "formula": {
            "terms": [
                {
                    "key": "offensive_production_component",
                    "value": 3.8,
                    "weight": 1.0,
                    "contribution": 3.8,
                    "status": "available",
                },
            ],
        },
        "offensive_production_component": {
            "value": 3.8,
            "inputs": [
                {
                    "key": "avg_sot_for",
                    "label": "Media tiri in porta fatti",
                    "raw_value": 3.9,
                    "normalized_value": 3.9,
                    "internal_weight": 0.30,
                    "internal_contribution": 1.17,
                    "source_path": "fixture_team_stats.shots_on_target",
                    "sample_count": 10,
                    "fallback_used": False,
                    "status": "available",
                },
            ],
            "quality": {"inputs_total": 9, "inputs_available": 9, "fallback_count": 0},
        },
    }
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V11_SOT,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=24.0,
        prediction_confidence=None,
    )
    sot_inp = next(r for r in trace if r.get("trace_key") == "v11_off_input_avg_sot_for")
    assert sot_inp["value"] == 3.9
    assert sot_inp["fallback_used"] is False
    term = next(r for r in trace if r.get("trace_key") == "v11_term_offensive_production_component")
    assert term["value"] == 3.8
    assert len([r for r in trace if is_countable_role(str(r.get("application_role")))]) == len(
        [s for s in manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT) if is_countable_role(s.application_role)],
    )
