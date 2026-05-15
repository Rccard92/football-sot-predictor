import pytest

from app.schemas.predictions import UpcomingSotCalculationBreakdown
from app.services.sot_line_evaluate import evaluate_match_sot_line
from app.services.sot_model_constants import WEIGHTS_BASELINE_V0_1
from app.services.sot_prediction_service import upcoming_calculation_breakdown_from_raw_json


def test_breakdown_contributions_match_weights():
    raw = {
        "weights": dict(WEIGHTS_BASELINE_V0_1),
        "inputs": {k: 4.0 for k in WEIGHTS_BASELINE_V0_1},
        "resolved_inputs": {k: 4.0 for k in WEIGHTS_BASELINE_V0_1},
        "expected_sot": 4.0,
        "league_pre_match_avg": 3.2,
    }
    bd = upcoming_calculation_breakdown_from_raw_json(raw)
    assert bd is not None
    validated = UpcomingSotCalculationBreakdown.model_validate(bd)
    s = 0.0
    for key in WEIGHTS_BASELINE_V0_1:
        w = WEIGHTS_BASELINE_V0_1[key]
        assert getattr(validated, f"{key}_contribution") == pytest.approx(4.0 * w, rel=1e-4)
        assert getattr(validated, f"{key}_fallback_used") is False
        s += getattr(validated, f"{key}_contribution")
    assert s == pytest.approx(4.0, rel=1e-3)
    assert validated.expected_sot_total == 4.0


def test_breakdown_fallback_flag_when_input_missing():
    inputs = {k: 4.0 for k in WEIGHTS_BASELINE_V0_1}
    inputs["last5_avg_sot_for"] = None
    resolved = {k: 4.0 for k in WEIGHTS_BASELINE_V0_1}
    raw = {
        "weights": dict(WEIGHTS_BASELINE_V0_1),
        "inputs": inputs,
        "resolved_inputs": resolved,
        "expected_sot": 4.0,
        "league_pre_match_avg": None,
    }
    bd = upcoming_calculation_breakdown_from_raw_json(raw)
    assert bd is not None
    assert bd["last5_avg_sot_for_fallback_used"] is True
    assert bd["last5_avg_sot_for_fallback_note"] is not None
    assert bd["season_avg_sot_for_fallback_used"] is False


def test_evaluate_match_line_example_totals_and_implied_prob():
    out = evaluate_match_sot_line(
        3.59,
        4.55,
        6.5,
        odds=1.50,
        bookmaker="Sisal Matchpoint",
        market_type="match_total_sot",
    )
    assert out["total_expected_sot"] == pytest.approx(8.14, rel=1e-4)
    assert out["gap"] == pytest.approx(1.64, rel=1e-4)
    assert out["suggestion"] == "over"
    assert out["strength"] == "forte"
    assert out["implied_probability"] == pytest.approx(66.67, rel=1e-3)
    assert out["bookmaker"] == "Sisal Matchpoint"
    assert "tiri in porta totali" in out["explanation"].lower()
