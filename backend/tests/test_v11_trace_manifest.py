"""Manifest e trace baseline_v1_1_sot stage 5 (xG)."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side


def test_v11_manifest_five_formula_thirty_one_inputs():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    formula_direct = [s for s in specs if s.application_role == "direct_formula_component"]
    comp_in = [s for s in specs if s.application_role == "component_input"]
    assert len(formula_direct) == 5
    keys = {s.trace_key for s in formula_direct}
    assert "v11_term_offensive_production_component" in keys
    assert "v11_term_opponent_defensive_resistance_component" in keys
    assert "v11_term_home_away_split_component" in keys
    assert "v11_term_recent_form_component" in keys
    assert "v11_term_xg_chance_quality_component" in keys
    assert len(comp_in) == 31
    off_in = [s for s in comp_in if s.parent_component == "offensive_production_component"]
    def_in = [s for s in comp_in if s.parent_component == "opponent_defensive_resistance_component"]
    split_in = [s for s in comp_in if s.parent_component == "home_away_split_component"]
    recent_in = [s for s in comp_in if s.parent_component == "recent_form_component"]
    xg_in = [s for s in comp_in if s.parent_component == "xg_chance_quality_component"]
    assert len(off_in) == 9
    assert len(def_in) == 6
    assert len(split_in) == 5
    assert len(recent_in) == 6
    assert len(xg_in) == 5


def test_v11_trace_from_saved_raw():
    raw = {
        "prediction_valid": True,
        "formula_quality_status": "ok",
        "formula": {
            "terms_count": 5,
            "terms": [
                {
                    "key": "offensive_production_component",
                    "value": 3.84,
                    "weight": 0.30,
                    "contribution": 1.15,
                    "status": "available",
                },
                {
                    "key": "opponent_defensive_resistance_component",
                    "value": 3.54,
                    "weight": 0.25,
                    "contribution": 0.89,
                    "status": "available",
                },
                {
                    "key": "home_away_split_component",
                    "value": 3.77,
                    "weight": 0.15,
                    "contribution": 0.57,
                    "status": "available",
                },
                {
                    "key": "recent_form_component",
                    "value": 3.60,
                    "weight": 0.15,
                    "contribution": 0.54,
                    "status": "available",
                },
                {
                    "key": "xg_chance_quality_component",
                    "value": 3.50,
                    "weight": 0.15,
                    "contribution": 0.53,
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
        "home_away_split_component": {
            "value": 3.77,
            "split_context": "home",
            "opponent_split_context": "away",
            "inputs": [
                {
                    "key": "split_avg_sot_for",
                    "label": "SOT fatti casa/fuori",
                    "raw_value": 4.0,
                    "normalized_value": 4.0,
                    "internal_weight": 0.30,
                    "internal_contribution": 1.20,
                    "source_path": "fixture_team_stats.shots_on_target (split casa/fuori squadra)",
                    "sample_count": 6,
                    "split_context": "home",
                    "fallback_used": False,
                    "status": "available",
                },
            ],
            "quality": {"inputs_total": 5, "inputs_available": 5, "fallback_count": 0},
        },
        "recent_form_component": {
            "value": 3.60,
            "inputs": [
                {
                    "key": "recent_avg_sot_for",
                    "label": "SOT fatti ultime 5",
                    "raw_value": 4.0,
                    "normalized_value": 4.0,
                    "internal_weight": 0.25,
                    "internal_contribution": 1.0,
                    "source_path": "x",
                    "sample_count": 5,
                    "fallback_used": False,
                    "status": "available",
                },
            ],
            "quality": {"inputs_total": 6, "inputs_available": 6, "fallback_count": 0},
        },
        "xg_chance_quality_component": {
            "value": 3.50,
            "inputs": [
                {
                    "key": "avg_xg_for",
                    "label": "xG prodotti",
                    "raw_value": 1.2,
                    "normalized_value": 3.4,
                    "internal_weight": 0.30,
                    "internal_contribution": 1.0,
                    "source_path": "fixture_team_stats.expected_goals",
                    "sample_count": 5,
                    "fallback_used": False,
                    "status": "available",
                },
            ],
            "quality": {"inputs_total": 5, "inputs_available": 5, "fallback_count": 0},
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
    split_inp = next(r for r in trace if r.get("trace_key") == "v11_split_input_split_avg_sot_for")
    assert split_inp["value"] == 4.0
    assert "home" in str(split_inp.get("notes") or "")
    recent_inp = next(r for r in trace if r.get("trace_key") == "v11_recent_input_recent_avg_sot_for")
    assert recent_inp["value"] == 4.0
    xg_inp = next(r for r in trace if r.get("trace_key") == "v11_xg_input_avg_xg_for")
    assert xg_inp["value"] == 3.4
    term_off = next(r for r in trace if r.get("trace_key") == "v11_term_offensive_production_component")
    assert term_off["value"] == 3.84
    term_split = next(r for r in trace if r.get("trace_key") == "v11_term_home_away_split_component")
    assert term_split["value"] == 3.77
    term_recent = next(r for r in trace if r.get("trace_key") == "v11_term_recent_form_component")
    assert term_recent["value"] == 3.60
    term_xg = next(r for r in trace if r.get("trace_key") == "v11_term_xg_chance_quality_component")
    assert term_xg["value"] == 3.50
    assert len([r for r in trace if is_countable_role(str(r.get("application_role")))]) == len(
        [s for s in manifest_for_model(BASELINE_SOT_MODEL_VERSION_V11_SOT) if is_countable_role(s.application_role)],
    )
