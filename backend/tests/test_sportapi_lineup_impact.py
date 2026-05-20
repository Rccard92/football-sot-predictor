"""Unit test simulazione Lineup Impact."""

from app.services.sportapi.sportapi_lineup_impact_service import _clamp_factor


def test_clamp_factor_probable():
    assert _clamp_factor(0.5, False) == 0.75
    assert _clamp_factor(1.5, False) == 1.20


def test_clamp_factor_official():
    assert _clamp_factor(0.5, True) == 0.65
    assert _clamp_factor(1.5, True) == 1.30


def test_lineup_confidence_weight_formula():
    lineup_weight = 0.60
    net_missing = 0.22
    raw_factor = 1.0 - (net_missing * lineup_weight)
    factor = _clamp_factor(raw_factor, False)
    assert 0.75 <= factor <= 1.20
    base = 4.8
    adjusted = round(base * factor, 2)
    assert adjusted < base
