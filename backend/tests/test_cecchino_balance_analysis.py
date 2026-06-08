"""Test analisi Equilibrio vs Squilibrio — Cecchino Fase 29."""

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
    assert out["f36"]["class_key"] == "strong_balance"


def test_f36_080_equilibrio_score_80():
    out = _build(quota_cecchino_1=2.50, quota_cecchino_2=3.30)
    assert out["f36"]["abs"] == pytest.approx(0.80, abs=0.001)
    assert out["f36"]["score"] == 80
    assert out["f36"]["class_key"] == "balance"


def test_f36_120_transizione_score_60():
    out = _build(quota_cecchino_1=2.50, quota_cecchino_2=3.70)
    assert out["f36"]["abs"] == pytest.approx(1.20, abs=0.001)
    assert out["f36"]["score"] == 60
    assert out["f36"]["class_key"] == "transition"


def test_f36_170_squilibrio_score_40():
    out = _build(quota_cecchino_1=2.50, quota_cecchino_2=4.20)
    assert out["f36"]["abs"] == pytest.approx(1.70, abs=0.001)
    assert out["f36"]["score"] == 40
    assert out["f36"]["class_key"] == "imbalance"


def test_dominance_is_max_minus_second():
    out = _build(prob_cecchino_1=39.0, prob_cecchino_x=23.0, prob_cecchino_2=38.0)
    assert out["dominance"]["value"] == pytest.approx(1.0, abs=0.01)


def test_dominance_2_equilibrio_estremo():
    out = _build(prob_cecchino_1=39.0, prob_cecchino_x=20.0, prob_cecchino_2=37.0)
    assert out["dominance"]["value"] == pytest.approx(2.0, abs=0.01)
    assert out["dominance"]["label"] == "Equilibrio estremo"
    assert out["dominance"]["stars"] == 1


def test_dominance_6_equilibrio_forte():
    out = _build(prob_cecchino_1=42.0, prob_cecchino_x=20.0, prob_cecchino_2=36.0)
    assert out["dominance"]["value"] == pytest.approx(6.0, abs=0.01)
    assert out["dominance"]["label"] == "Equilibrio forte"
    assert out["dominance"]["stars"] == 2


def test_dominance_12_tendenza():
    out = _build(prob_cecchino_1=45.0, prob_cecchino_x=20.0, prob_cecchino_2=33.0)
    assert out["dominance"]["value"] == pytest.approx(12.0, abs=0.01)
    assert out["dominance"]["label"] == "Tendenza"
    assert out["dominance"]["stars"] == 3


def test_dominance_20_squilibrio():
    out = _build(prob_cecchino_1=50.0, prob_cecchino_x=15.0, prob_cecchino_2=30.0)
    assert out["dominance"]["value"] == pytest.approx(20.0, abs=0.01)
    assert out["dominance"]["label"] == "Squilibrio"
    assert out["dominance"]["stars"] == 4


def test_dominance_30_squilibrio_forte():
    out = _build(prob_cecchino_1=55.0, prob_cecchino_x=15.0, prob_cecchino_2=20.0)
    assert out["dominance"]["value"] == pytest.approx(35.0, abs=0.01)
    assert out["dominance"]["label"] == "Squilibrio forte"
    assert out["dominance"]["stars"] == 5


def test_quota_x_310_pareggio_forte():
    out = _build(quota_cecchino_x=3.10)
    assert out["draw"]["label"] == "Pareggio forte"
    assert out["draw"]["class_key"] == "strong_draw"


def test_quota_x_340_pareggio_possibile():
    out = _build(quota_cecchino_x=3.40)
    assert out["draw"]["label"] == "Pareggio possibile"
    assert out["draw"]["class_key"] == "possible_draw"


def test_quota_x_390_pareggio_debole():
    out = _build(quota_cecchino_x=3.90)
    assert out["draw"]["label"] == "Pareggio debole"
    assert out["draw"]["class_key"] == "weak_draw"


def test_quota_x_450_pareggio_poco_probabile():
    out = _build(quota_cecchino_x=4.50)
    assert out["draw"]["label"] == "Pareggio poco probabile"
    assert out["draw"]["class_key"] == "unlikely_draw"


def test_operational_x_molto_forte():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=2.90,
        quota_cecchino_x=3.20,
        prob_cecchino_1=39.0,
        prob_cecchino_x=23.0,
        prob_cecchino_2=38.0,
    )
    assert out["operational"]["label"] == "X molto forte"
    assert out["operational"]["class_key"] == "very_strong_draw_under"
    assert out["technical"]["rule_id"] == 1


def test_operational_falso_equilibrio():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=2.90,
        quota_cecchino_x=3.80,
        prob_cecchino_1=50.0,
        prob_cecchino_x=15.0,
        prob_cecchino_2=30.0,
    )
    assert out["operational"]["label"] == "Falso equilibrio"
    assert out["operational"]["class_key"] == "false_balance"
    assert out["summary"]["is_false_balance"] is True


def test_operational_squilibrio_confermato():
    out = _build(
        quota_cecchino_1=2.50,
        quota_cecchino_2=4.50,
        quota_cecchino_x=3.80,
        prob_cecchino_1=50.0,
        prob_cecchino_x=15.0,
        prob_cecchino_2=30.0,
    )
    assert out["operational"]["label"] == "Squilibrio confermato"
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
    assert out["inputs"]["prob_x"] == pytest.approx(43.24, abs=0.01)


def test_build_from_final_unavailable():
    out = build_balance_analysis_from_final({"status": "insufficient_data"})
    assert out["status"] == "insufficient_data"
