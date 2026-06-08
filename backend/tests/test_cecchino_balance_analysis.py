"""Test analisi Equilibrio vs Squilibrio — Cecchino Fase 29/30."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_balance_analysis import (
    VERSION,
    build_balance_analysis_from_final,
    build_cecchino_balance_analysis,
)


def _build(**kwargs):
    defaults = {
        "quota_cecchino_1": 2.50,
        "quota_cecchino_x": 3.20,
        "quota_cecchino_2": 2.90,
        "prob_cecchino_1": 39.0,
        "prob_cecchino_x": 23.0,
        "prob_cecchino_2": 38.0,
    }
    defaults.update(kwargs)
    return build_cecchino_balance_analysis(**defaults)


def test_version_is_v2():
    out = _build()
    assert out["version"] == "cecchino_balance_analysis_v2"
    assert VERSION == "cecchino_balance_analysis_v2"


def test_f36_signed_is_quota2_minus_quota1():
    out = _build(quota_cecchino_1=2.82, quota_cecchino_2=7.77)
    assert out["f36"]["signed"] == pytest.approx(7.77 - 2.82, abs=0.001)


def test_f36_abs_is_absolute():
    out = _build(quota_cecchino_1=3.00, quota_cecchino_2=2.60)
    assert out["f36"]["abs"] == pytest.approx(0.40, abs=0.001)
    assert out["f36"]["signed"] == pytest.approx(-0.40, abs=0.001)


def test_f36_040_equilibrio_forte_score_100():
    out = _build(quota_cecchino_1=2.50, quota_cecchino_2=2.90)
    assert out["f36"]["abs"] == pytest.approx(0.40, abs=0.001)
    assert out["f36"]["score"] == 100
    assert out["f36"]["label"] == "Equilibrio forte"


def test_dominance_formula_unchanged():
    out = _build(prob_cecchino_1=31.0, prob_cecchino_x=42.0, prob_cecchino_2=27.0)
    assert out["dominance"]["value"] == pytest.approx(11.0, abs=0.01)


def test_draw_dominance_12_reinforces_balance():
    out = _build(prob_cecchino_1=31.0, prob_cecchino_x=42.0, prob_cecchino_2=27.0)
    ctx = out["dominance_context"]
    assert ctx["best_side"] == "DRAW"
    assert ctx["best_side_label"] == "X"
    assert ctx["dominance_value"] == pytest.approx(11.0, abs=0.01)
    assert ctx["effect_on_balance"] == "reinforces_balance"
    assert ctx["label"] == "X forte"


def test_home_dominance_12_weakens_balance():
    out = _build(prob_cecchino_1=45.0, prob_cecchino_x=20.0, prob_cecchino_2=33.0)
    ctx = out["dominance_context"]
    assert ctx["best_side"] == "HOME"
    assert ctx["dominance_value"] == pytest.approx(12.0, abs=0.01)
    assert ctx["effect_on_balance"] == "weakens_balance"
    assert ctx["label"] == "Tendenza laterale"


def test_away_dominance_20_confirms_imbalance():
    out = _build(prob_cecchino_1=30.0, prob_cecchino_x=15.0, prob_cecchino_2=50.0)
    ctx = out["dominance_context"]
    assert ctx["best_side"] == "AWAY"
    assert ctx["dominance_value"] == pytest.approx(20.0, abs=0.01)
    assert ctx["effect_on_balance"] == "confirms_imbalance"
    assert ctx["label"] == "Squilibrio laterale"


def test_low_f36_high_dom_draw_not_false_balance():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=2.90,
        quota_cecchino_x=3.20,
        prob_cecchino_1=31.0,
        prob_cecchino_x=42.0,
        prob_cecchino_2=27.0,
    )
    assert out["operational"]["class_key"] == "very_strong_draw_balance"
    assert out["operational"]["label"] == "X molto forte"
    assert out["summary"]["is_false_balance"] is False
    assert out["summary"]["is_x_dominance"] is True
    assert out["cross_reading"]["label"] == "X forte / equilibrio rafforzato"


def test_low_f36_high_dom_home_false_balance():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=2.90,
        quota_cecchino_x=3.80,
        prob_cecchino_1=50.0,
        prob_cecchino_x=15.0,
        prob_cecchino_2=30.0,
    )
    assert out["operational"]["class_key"] == "false_balance"
    assert out["summary"]["is_false_balance"] is True
    assert out["summary"]["is_x_dominance"] is False


def test_low_f36_high_dom_away_false_balance():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=2.90,
        quota_cecchino_x=3.80,
        prob_cecchino_1=30.0,
        prob_cecchino_x=15.0,
        prob_cecchino_2=50.0,
    )
    assert out["operational"]["class_key"] == "false_balance"
    assert out["summary"]["is_false_balance"] is True


def test_side_probability_gap_value():
    out = _build(prob_cecchino_1=35.4, prob_cecchino_x=30.0, prob_cecchino_2=34.1)
    assert out["side_probability_gap"]["value"] == pytest.approx(1.3, abs=0.01)


def test_side_probability_gap_2_extreme():
    out = _build(prob_cecchino_1=40.0, prob_cecchino_x=20.0, prob_cecchino_2=38.0)
    assert out["side_probability_gap"]["value"] == pytest.approx(2.0, abs=0.01)
    assert out["side_probability_gap"]["class_key"] == "side_balance_extreme"


def test_side_probability_gap_10_tendency():
    out = _build(prob_cecchino_1=45.0, prob_cecchino_x=20.0, prob_cecchino_2=35.0)
    assert out["side_probability_gap"]["value"] == pytest.approx(10.0, abs=0.01)
    assert out["side_probability_gap"]["class_key"] == "side_tendency"


def test_summary_is_x_dominance_true_when_draw():
    out = _build(prob_cecchino_1=31.0, prob_cecchino_x=42.0, prob_cecchino_2=27.0)
    assert out["summary"]["is_x_dominance"] is True
    assert out["summary"]["is_false_balance"] is False


def test_quota_x_classification_unchanged():
    out = _build(quota_cecchino_x=3.10)
    assert out["draw"]["label"] == "Pareggio forte"
    out2 = _build(quota_cecchino_x=4.50)
    assert out2["draw"]["label"] == "Pareggio poco probabile"


def test_confirmed_imbalance_lateral():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=4.50,
        quota_cecchino_x=3.80,
        prob_cecchino_1=50.0,
        prob_cecchino_x=15.0,
        prob_cecchino_2=30.0,
    )
    assert out["operational"]["class_key"] == "confirmed_imbalance"
    assert out["summary"]["is_confirmed_imbalance"] is True


def test_insufficient_data_missing_inputs():
    out = build_cecchino_balance_analysis(
        quota_cecchino_1=2.5,
        quota_cecchino_x=None,
        quota_cecchino_2=3.0,
        prob_cecchino_1=0.4,
        prob_cecchino_x=0.3,
        prob_cecchino_2=0.3,
    )
    assert out["status"] == "insufficient_data"
    assert "missing_cecchino_1x2_inputs" in out["warnings"]


def test_build_from_final_decimal_probs():
    final = {
        "status": "available",
        "quota_1": 2.82,
        "quota_x": 2.31,
        "quota_2": 7.77,
        "prob_1": 0.3545,
        "prob_x": 0.4324,
        "prob_2": 0.1286,
        "prob_1_pct": 35.45,
        "prob_x_pct": 43.24,
        "prob_2_pct": 12.86,
    }
    out = build_balance_analysis_from_final(final)
    assert out["status"] == "available"
    assert out["version"] == VERSION
    assert out["dominance_context"]["best_side"] == "DRAW"
    assert out["inputs"]["prob_x"] == pytest.approx(43.24, abs=0.01)


def test_build_from_final_unavailable():
    out = build_balance_analysis_from_final({"status": "insufficient_data"})
    assert out["status"] == "insufficient_data"
