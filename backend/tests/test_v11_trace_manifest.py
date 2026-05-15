"""Manifest e trace baseline_v1_1_sot stage 2."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side


def test_v11_manifest_two_formula_fifteen_inputs():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    formula_direct = [s for s in specs if s.application_role == "direct_formula_component"]
    comp_in = [s for s in specs if s.application_role == "component_input"]
    assert len(formula_direct) == 2
    keys = {s.trace_key for s in formula_direct}
    assert "v11_term_offensive_production_component" in keys
    assert "v11_term_opponent_defensive_resistance_component" in keys
    assert len(comp_in) == 15
    off_in = [s for s in comp_in if s.parent_component == "offensive_production_component"]
    def_in = [s for s in comp_in if s.parent_component == "opponent_defensive_resistance_component"]
    assert len(off_in) == 9
    assert len(def_in) == 6


def test_v11_trace_from_saved_raw():
    raw = {
        "prediction_valid": True,
        "formula_quality_status": "ok",
        "formula": {
            "terms_count": 2,
            "terms": [
                {
                    "key": "offensive_production_component",
                    "value": 3.84,
                    "weight": 0.60,
                    "contribution": 2.30,
                    "status": "available",
                },
                {
                    "key": "opponent_defensive_resistance_component",
                    "value": 3.54,
                    "weight": 0.40,
                    "contribution": 1.42,
                    "status": "available",
                },
            ],
        },
        "offensive_production_component": {
            "value": 3.84,
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
        "opponent_defensive_resistance_component": {
            "value": 3.54,
            "inputs": [
                {
                    "key": "opponent_avg_sot_conceded",
                    "label": "SOT concessi avversario stagione",
                    "raw_value": 3.5,
                    "normalized_value": 3.5,
                    "internal_weight": 0.35,
                    "internal_contribution": 1.23,
                    "source_path": "fixture_team_stats.shots_on_target (avversari dell'avversario)",
                    "sample_count": 8,
                    "fallback_used": False,
                    "status": "available",
                },
            ],
            "quality": {"inputs_total": 6, "inputs_available": 6, "fallback_count": 0},
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
    def_inp = next(r for r in trace if r.get("trace_key") == "v11_def_input_opponent_avg_sot_conceded")
    assert def_inp["value"] == 3.5
    term_off = next(r for r in trace if r.get("trace_key") == "v11_term_offensive_production_component")
    assert term_off["value"] == 3.84
    term_def = next(r for r in trace if r.get("trace_key") == "v11_term_opponent_defensive_resistance_component")
    assert term_def["value"] == 3.54
    assert len([r for r in trace if is_countable_role(str(r.get("application_role")))]) == len(
        [s for s in manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT) if is_countable_role(s.application_role)],
    )
