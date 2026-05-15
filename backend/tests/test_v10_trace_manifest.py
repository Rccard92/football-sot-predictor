"""Test manifest e trace v1.0 (componente offensivo composita)."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V10_SOT
from app.services.model_applied_variable_manifest import is_countable_role, manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side


def _sample_v10_raw() -> dict:
    offensive_inputs = [
        {
            "key": "avg_sot_for",
            "label": "Media tiri in porta fatti",
            "raw_value": 3.89,
            "normalized_value": 3.89,
            "internal_weight": 0.30,
            "internal_contribution": 1.167,
            "source_path": "fixture_team_stats.shots_on_target",
            "sample_count": 34,
            "fallback_used": False,
        },
        {
            "key": "avg_total_shots_for",
            "label": "Media tiri totali fatti",
            "raw_value": 11.56,
            "normalized_value": 3.72,
            "internal_weight": 0.18,
            "internal_contribution": 0.6696,
            "source_path": "fixture_team_stats.total_shots",
            "sample_count": 34,
            "fallback_used": False,
        },
    ]
    for k, w in (
        ("shot_accuracy_for", 0.14),
        ("avg_inside_box_shots_for", 0.14),
        ("avg_outside_box_shots_for", 0.05),
        ("avg_blocked_shots_for", 0.05),
        ("avg_shots_off_goal_for", 0.04),
        ("avg_goals_for", 0.05),
        ("offensive_trend", 0.05),
    ):
        offensive_inputs.append(
            {
                "key": k,
                "label": k,
                "raw_value": 1.0,
                "normalized_value": 3.5,
                "internal_weight": w,
                "internal_contribution": 3.5 * w,
                "source_path": f"fixture_team_stats.{k}",
                "sample_count": 10,
                "fallback_used": False,
            },
        )
    return {
        "architecture": "feature_registry_explicit_terms_plus_xg",
        "offensive_production_component": {
            "key": "offensive_production_component",
            "label": "Produzione offensiva composita",
            "value": 3.84,
            "weight_in_final_formula": 0.30,
            "contribution_in_final_formula": 1.152,
            "formula": "offensive_production_component = ...",
            "inputs": offensive_inputs,
            "quality": {"inputs_total": 9, "inputs_available": 9, "fallback_count": 0, "missing_inputs": []},
            "fallbacks_used": [],
        },
        "formula": {
            "terms": [
                {
                    "key": "offensive_production_component",
                    "value": 3.84,
                    "weight": 0.30,
                    "contribution": 1.152,
                },
                {"key": "opp_avg_sot_conceded", "value": 4.0, "weight": 0.25, "contribution": 1.0},
                {"key": "team_split_avg_sot_for", "value": 3.5, "weight": 0.15, "contribution": 0.525},
                {"key": "opp_split_avg_sot_conceded", "value": 3.6, "weight": 0.10, "contribution": 0.36},
                {"key": "team_last5_avg_sot_for", "value": 3.7, "weight": 0.10, "contribution": 0.37},
                {"key": "opp_last5_avg_sot_conceded", "value": 3.8, "weight": 0.10, "contribution": 0.38},
                {"key": "expected_goals", "value": 1.2, "weight": 0.10, "contribution": 0.15},
            ],
        },
        "xg_component": {
            "xg_adjustment_applied": True,
            "team_avg_xg_for": 1.2,
            "xg_adjustment_sot": 0.15,
            "fallback_used": False,
        },
    }


def test_v10_manifest_has_seven_formula_roles_and_nine_component_inputs():
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V10_SOT)
    formula_direct = [s for s in specs if s.application_role == "direct_formula_component"]
    comp_in = [s for s in specs if s.application_role == "component_input"]
    assert len(formula_direct) == 7
    assert len(comp_in) == 9
    assert all(s.parent_component == "offensive_production_component" for s in comp_in)


def test_v10_trace_offensive_input_reads_list():
    raw = _sample_v10_raw()
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V10_SOT,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=24.0,
        prediction_confidence=None,
    )
    sot_inp = next(r for r in trace if r.get("trace_key") == "v10_off_input_avg_sot_for")
    assert sot_inp["value"] == 3.89
    assert sot_inp["application_role"] == "component_input"
    assert sot_inp["parent_component"] == "offensive_production_component"
    formula_rows = [r for r in trace if r.get("application_role") == "direct_formula_component"]
    assert len(formula_rows) == 7
    assert len([r for r in trace if is_countable_role(str(r.get("application_role")))]) == len(
        [s for s in manifest_for_model(BASELINE_SOT_MODEL_VERSION_V10_SOT) if is_countable_role(s.application_role)],
    )
