"""Unit test simulazione Lineup Impact."""

from app.services.sportapi.sportapi_lineup_impact_logic import clamp_factor


def test_clamp_factor_probable():
    assert clamp_factor(0.5, False) == 0.75
    assert clamp_factor(1.5, False) == 1.15


def test_clamp_factor_official():
    assert clamp_factor(0.5, True) == 0.65
    assert clamp_factor(1.5, True) == 1.20


def test_lineup_confidence_weight_formula():
    lineup_weight = 0.60
    net_loss = 0.22
    raw_factor = 1.0 - (net_loss * lineup_weight)
    factor = clamp_factor(raw_factor, False)
    assert 0.75 <= factor <= 1.15
    base = 4.8
    adjusted = round(base * factor, 2)
    assert adjusted < base
