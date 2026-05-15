"""Test correzione xG additiva v1.0 (senza DB)."""

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
)
from app.services.model_applied_variable_manifest import manifest_for_model
from app.services.predictions_v10.explicit_terms_from_v04 import (
    build_formula_payload_v10,
    build_xg_formula_term,
)
from app.services.predictions_v10.xg_adjustment_component import (
    XG_ADJ_CAP,
    XG_SENSITIVITY,
    _clamp,
)


def test_clamp_xg_pct_cap():
    assert _clamp(0.15, -XG_ADJ_CAP, XG_ADJ_CAP) == XG_ADJ_CAP
    assert _clamp(-0.12, -XG_ADJ_CAP, XG_ADJ_CAP) == -XG_ADJ_CAP


def test_additive_adjustment_sot():
    base = 3.37
    pct = 0.0158
    adj = round(base * pct, 2)
    assert adj == 0.05
    assert round(base + adj, 2) == 3.42


def test_build_xg_formula_term_fallback():
    xc = {
        "team_avg_xg_for": None,
        "xg_adjustment_applied": False,
        "fallback_used": True,
        "xg_adjustment_sot": 0.0,
        "cap_applied": False,
        "source": "fixtures/statistics::expected_goals",
    }
    term = build_xg_formula_term(xc)
    assert term["key"] == "expected_goals"
    assert term["status"] == "fallback"
    assert term["contribution"] == 0.0
    assert term["weight"] == XG_SENSITIVITY


def test_build_xg_formula_term_applied():
    xc = {
        "team_avg_xg_for": 1.62,
        "xg_adjustment_applied": True,
        "fallback_used": False,
        "xg_adjustment_sot": 0.11,
        "cap_applied": False,
        "source": "fixtures/statistics::expected_goals",
    }
    term = build_xg_formula_term(xc)
    assert term["status"] == "available"
    assert term["contribution"] == 0.11
    assert term["value"] == 1.62


def test_formula_payload_seven_terms():
    base_terms = [{"key": f"t{i}", "value": 1.0, "weight": 0.1, "contribution": 0.1} for i in range(6)]
    xc = {
        "team_avg_xg_for": 1.5,
        "xg_adjustment_applied": True,
        "fallback_used": False,
        "xg_adjustment_sot": 0.11,
        "cap_applied": False,
        "source": "fixtures/statistics::expected_goals",
    }
    payload = build_formula_payload_v10(
        base_terms,
        base_explicit_sot=3.37,
        xg_component=xc,
        final_sot=3.48,
    )
    assert payload["type"] == "explicit_weighted_sum_plus_adjustments"
    assert payload["base_terms_count"] == 6
    assert payload["adjustment_terms_count"] == 1
    assert len(payload["terms"]) == 7
    assert payload["base_sum"] == 3.37
    assert payload["adjustment_sum"] == 0.11
    assert payload["final_sum"] == 3.48
    assert "xG_adjustment" in payload["symbolic"]


def test_manifest_v10_includes_expected_goals():
    m4 = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT)
    m10 = manifest_for_model(BASELINE_SOT_MODEL_VERSION_V10_SOT)
    assert len(m10) == len(m4) + 1
    assert any(s.trace_key == "v10_expected_goals" for s in m10)
