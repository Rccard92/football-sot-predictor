"""Builder termini espliciti v1.0 da raw_json v0.4 (senza DB)."""

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V10_SOT
from app.services.model_applied_variable_manifest import manifest_for_model
from app.services.model_applied_variable_trace import build_applied_variable_trace_side, validate_model_trace
from app.services.predictions_v10.explicit_terms_from_v04 import (
    alignment_status,
    build_explicit_v04_terms_from_saved_raw,
)


def _sample_raw_v04() -> dict:
    return {
        "offensive_production_component": {
            "value": 3.5,
            "weight_in_model": 0.30,
            "inputs": {},
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


def test_build_explicit_terms_six_weights():
    terms, expected, quality = build_explicit_v04_terms_from_saved_raw(_sample_raw_v04())
    assert len(terms) == 6
    assert terms[0]["key"] == "offensive_production_component"
    assert terms[0]["weight"] == 0.30
    assert all(t.get("source_path") for t in terms)
    wmap = {t["key"]: t["weight"] for t in terms[1:]}
    assert wmap["opp_avg_sot_conceded"] == 0.25
    assert abs(expected - 3.30) < 1e-6
    assert quality.get("formula_quality_status") == "ok"


def test_alignment_status_thresholds():
    assert alignment_status(0.02) == "aligned_with_v04"
    assert alignment_status(0.05) == "minor_rounding_difference"
    assert alignment_status(0.15) == "needs_review"


def test_manifest_v10_matches_v04_length():
    from app.core.constants import BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT

    m4 = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT)
    m10 = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V10_SOT)
    assert len(m10) == len(m4) + 1


def test_trace_v10_same_length_as_manifest():
    raw = _sample_raw_v04()
    raw["formula"] = {"type": "weighted_sum", "terms": []}
    trace = build_applied_variable_trace_side(
        BASELINE_SOT_MODEL_VERSION_V10_SOT,
        raw,
        team_id=1,
        team_name="Test",
        audit_map={},
        hours_to_kickoff=12.0,
        prediction_confidence=80,
    )
    specs = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V10_SOT)
    assert len(trace) == len(specs)
    val = validate_model_trace(BASELINE_SOT_MODEL_VERSION_V10_SOT, raw, trace, stored_predicted_sot=3.30, sum_contributions=3.30)
    assert val.get("missing_trace_keys") == []
