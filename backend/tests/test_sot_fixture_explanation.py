import pytest

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
)
from app.services.sot_prediction_service import WEIGHTS_BASELINE_V0_1
from app.services.sot_fixture_explanation_service import (
    V03_COMPONENT_META,
    _build_prediction_formula_breakdown_side,
    _components_v01,
    _internal_formula_v04_offensive,
    _outcome_sot,
    _post_audit_judgment,
)


def test_outcome_sot_buckets():
    assert _outcome_sot(0.1) == "Centrata"
    assert _outcome_sot(0.5) == "Vicina"
    assert _outcome_sot(1.0) == "Da controllare"
    assert _outcome_sot(2.0) == "Errata"


def test_post_audit_judgment_buckets():
    assert _post_audit_judgment(0.4) == "Ottima"
    assert _post_audit_judgment(0.9) == "Vicina"
    assert _post_audit_judgment(1.2) == "Accettabile"
    assert _post_audit_judgment(2.0) == "Da analizzare"


def test_components_v01_length_and_contribution():
    raw = {
        "weights": dict(WEIGHTS_BASELINE_V0_1),
        "resolved_inputs": {k: 4.0 for k in WEIGHTS_BASELINE_V0_1},
        "inputs": {k: 4.0 for k in WEIGHTS_BASELINE_V0_1},
        "expected_sot": 4.0,
    }
    comps = _components_v01(raw, 4.0)
    assert len(comps) == len(WEIGHTS_BASELINE_V0_1)
    s = sum(float(c["contribution"]) for c in comps)
    assert s == pytest.approx(4.0, rel=1e-3)


def test_prediction_formula_breakdown_v03_checksum():
    raw: dict = {
        "weights": {t[2]: t[3] for t in V03_COMPONENT_META},
        "components": {t[2]: {"value": 4.0, "formula": f"{t[2]} (stored)"} for t in V03_COMPONENT_META},
    }
    out = _build_prediction_formula_breakdown_side(BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, raw, 4.0)
    assert out is not None
    assert out["checksum_warning"] is None
    assert out["sum_contributions"] == pytest.approx(4.0, rel=1e-3)


def test_prediction_formula_breakdown_v03_warning_when_mismatch():
    raw: dict = {
        "weights": {t[2]: t[3] for t in V03_COMPONENT_META},
        "components": {t[2]: {"value": 4.0, "formula": "x"} for t in V03_COMPONENT_META},
    }
    out = _build_prediction_formula_breakdown_side(BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, raw, 5.0)
    assert out is not None
    assert out["checksum_warning"] is not None


def test_prediction_formula_breakdown_v01():
    raw = {
        "weights": dict(WEIGHTS_BASELINE_V0_1),
        "resolved_inputs": {k: 3.0 for k in WEIGHTS_BASELINE_V0_1},
        "inputs": {k: 3.0 for k in WEIGHTS_BASELINE_V0_1},
    }
    out = _build_prediction_formula_breakdown_side(BASELINE_SOT_MODEL_VERSION, raw, 3.0)
    assert out is not None
    assert len(out["terms"]) == 6


def test_prediction_formula_breakdown_v04():
    raw = {
        "offensive_production_component": {
            "value": 3.0,
            "weight_in_model": 0.30,
            "fallbacks_used": [],
            "cap_applied": False,
            "inputs": {},
        },
        "debug": {
            "baseline_other_inputs": {
                "opp_avg_sot_conceded": 3.0,
                "team_split_avg_sot_for": 3.0,
                "opp_split_avg_sot_conceded": 3.0,
                "team_last5_avg_sot_for": 3.0,
                "opp_last5_avg_sot_conceded": 3.0,
            },
        },
    }
    out = _build_prediction_formula_breakdown_side(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, raw, 3.0)
    assert out is not None
    assert len(out["terms"]) == 6
    assert out["checksum_warning"] is None


def test_internal_v04_offensive_notes_when_cap():
    comp = {
        "value": 3.0,
        "cap_applied": True,
        "inputs": {"avg_sot_for": {"value": 4.0, "weight": 0.35, "contribution": 1.4}},
        "fallbacks_used": [],
    }
    raw_root = {"debug": {"raw_component_value": 4.2, "cap_bounds": {"min": 2.25, "max": 3.75}}}
    out = _internal_formula_v04_offensive(comp, raw_root)
    assert any("grezzo" in n.lower() or "cap" in n.lower() for n in out["notes"])
