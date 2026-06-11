"""Test Intensità Goal — Cecchino Fase 46."""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE, STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    VERSION,
    _classify_delta,
    _classify_ratio,
    build_cecchino_goal_intensity_analysis_from_parity,
)


def _blocks(q39: float, r39: float, q42: float, r42: float) -> dict:
    ha_val = round((q39 + r39) / 2, 4)
    tot_val = round((q42 + r42) / 2, 4)
    return {
        "home_away": {
            "home_component": q39,
            "away_component": r39,
            "block_value": ha_val,
        },
        "totals": {
            "home_component": q42,
            "away_component": r42,
            "block_value": tot_val,
        },
    }


def _ft_parity(blocks: dict) -> dict:
    return {
        "status": STATUS_AVAILABLE,
        "blocks": blocks,
    }


def test_offensive_and_defensive_index_from_spec():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = _ft_parity(_blocks(2, 2, 1, 1))
    result = build_cecchino_goal_intensity_analysis_from_parity(over_ft=over, under_ft=under)

    assert result["status"] == STATUS_AVAILABLE
    assert result["offensive_index"] == pytest.approx(5.0)
    assert result["defensive_index"] == pytest.approx(3.0)
    assert result["intensity_ratio"] == pytest.approx(1.67, abs=0.01)
    assert result["intensity_delta"] == pytest.approx(2.0)
    assert result["ratio_class_key"] == "very_offensive"
    assert result["ratio_label"] == "Molto Offensiva"
    assert result["delta_class_key"] == "strong_offensive_push"
    assert result["delta_label"] == "Forte Spinta Offensiva"
    assert result["final_class_key"] == "very_offensive"
    assert result["final_label"] == "Molto Offensiva"


@pytest.mark.parametrize(
    ("ratio", "expected_key", "expected_label"),
    [
        (0.69, "very_defensive", "Molto Difensiva"),
        (0.70, "defensive", "Difensiva"),
        (0.89, "defensive", "Difensiva"),
        (0.90, "balanced", "Equilibrata"),
        (1.05, "balanced", "Equilibrata"),
        (1.06, "offensive", "Offensiva"),
        (1.20, "offensive", "Offensiva"),
        (1.21, "very_offensive", "Molto Offensiva"),
    ],
)
def test_ratio_thresholds(ratio: float, expected_key: str, expected_label: str):
    key, label = _classify_ratio(ratio)
    assert key == expected_key
    assert label == expected_label


@pytest.mark.parametrize(
    ("delta", "expected_key", "expected_label"),
    [
        (0.51, "strong_offensive_push", "Forte Spinta Offensiva"),
        (0.20, "moderate_offensive_push", "Moderata Spinta Offensiva"),
        (0.00, "neutral_zone", "Zona Neutra"),
        (-0.20, "moderate_defensive_push", "Moderata Spinta Difensiva"),
        (-0.51, "strong_defensive_push", "Forte Spinta Difensiva"),
    ],
)
def test_delta_thresholds(delta: float, expected_key: str, expected_label: str):
    key, label = _classify_delta(delta)
    assert key == expected_key
    assert label == expected_label


def test_defensive_zero_ratio_is_zero():
    over = _ft_parity(_blocks(2, 2, 1, 1))
    under = _ft_parity(_blocks(0, 0, 0, 0))
    result = build_cecchino_goal_intensity_analysis_from_parity(over_ft=over, under_ft=under)
    assert result["intensity_ratio"] == 0.0


def test_missing_under_sources_insufficient_data():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = {"status": STATUS_INSUFFICIENT_DATA, "blocks": None}
    result = build_cecchino_goal_intensity_analysis_from_parity(over_ft=over, under_ft=under)

    assert result["status"] == STATUS_INSUFFICIENT_DATA
    assert result["offensive_index"] is None
    assert result["defensive_index"] is None
    assert result["final_label"] == "Dati insufficienti"
    assert "missing_under_q44_sources" in result["warnings"]


def test_independence_from_balance_analysis():
    mod = importlib.import_module("app.services.cecchino.cecchino_goal_intensity_analysis")
    source = inspect.getsource(mod)
    assert "cecchino_balance_analysis" not in source
    assert "build_cecchino_balance_analysis" not in source
    assert "build_balance_analysis_from_final" not in source


def test_version_constant():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = _ft_parity(_blocks(2, 2, 1, 1))
    result = build_cecchino_goal_intensity_analysis_from_parity(over_ft=over, under_ft=under)
    assert result["version"] == VERSION
