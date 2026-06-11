"""Test Intensità Goal — Cecchino Fase 46/47."""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_BASELINE,
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


def _baseline(over: float, under: float, source: str = "league", sample: int = 50) -> dict:
    return {
        "source": source,
        "sample_size": sample,
        "baseline_over_q44": over,
        "baseline_under_q44": under,
        "method": "median",
    }


def test_raw_indices_from_spec():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = _ft_parity(_blocks(2, 2, 1, 1))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        baseline=_baseline(2.5, 2.5),
    )

    assert result["status"] == STATUS_AVAILABLE
    assert result["raw"]["offensive_index"] == pytest.approx(5.0)
    assert result["raw"]["defensive_index"] == pytest.approx(3.0)
    assert result["raw"]["raw_ratio"] == pytest.approx(1.67, abs=0.01)


def test_normalization_spec():
    over = _ft_parity(_blocks(1.2, 1.2, 0.6, 0.6))  # raw off = 1.8
    under = _ft_parity(_blocks(1.5, 1.5, 1.5, 1.5))  # raw def = 3.0
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        baseline=_baseline(1.50, 3.00),
    )

    norm = result["normalized"]
    assert norm["offensive_index"] == pytest.approx(1.20)
    assert norm["defensive_index"] == pytest.approx(1.00)
    assert norm["intensity_ratio"] == pytest.approx(1.20)
    assert norm["intensity_delta"] == pytest.approx(0.20)
    assert result["ratio_label"] == "Offensiva"
    assert result["delta_label"] == "Moderata Spinta Offensiva"
    assert result["final_label"] == "Offensiva"


def test_misleading_raw_ratio_vs_calibrated():
    over = _ft_parity(_blocks(1.2, 1.2, 0.6, 0.6))
    under = _ft_parity(_blocks(1.5, 1.5, 1.5, 1.5))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        baseline=_baseline(1.50, 3.00),
    )

    assert result["raw"]["raw_ratio"] == pytest.approx(0.60)
    _, raw_label = _classify_ratio(result["raw"]["raw_ratio"])
    assert raw_label == "Molto Difensiva"
    assert result["normalized"]["intensity_ratio"] == pytest.approx(1.20)
    assert result["final_label"] == "Offensiva"


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
def test_ratio_thresholds_on_calibrated(ratio: float, expected_key: str, expected_label: str):
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
def test_delta_thresholds_on_calibrated(delta: float, expected_key: str, expected_label: str):
    key, label = _classify_delta(delta)
    assert key == expected_key
    assert label == expected_label


def test_insufficient_baseline_when_baseline_null():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = _ft_parity(_blocks(2, 2, 1, 1))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        baseline={
            "source": None,
            "sample_size": 0,
            "baseline_over_q44": None,
            "baseline_under_q44": None,
            "method": "median",
        },
    )

    assert result["status"] == STATUS_INSUFFICIENT_BASELINE
    assert result["normalized"] is None
    assert result["final_label"] == "Baseline insufficiente"
    assert "insufficient_goal_intensity_baseline" in result["warnings"]
    assert result["raw"]["offensive_index"] == pytest.approx(5.0)


def test_missing_under_sources_insufficient_data():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = {"status": STATUS_INSUFFICIENT_DATA, "blocks": None}
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        baseline=_baseline(1.5, 3.0),
    )

    assert result["status"] == STATUS_INSUFFICIENT_DATA
    assert result["raw"] is None
    assert result["final_label"] == "Dati insufficienti"


def test_independence_from_balance_analysis():
    mod = importlib.import_module("app.services.cecchino.cecchino_goal_intensity_analysis")
    source = inspect.getsource(mod)
    assert "cecchino_balance_analysis" not in source
    assert "build_cecchino_balance_analysis" not in source


def test_version_v2():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = _ft_parity(_blocks(2, 2, 1, 1))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        baseline=_baseline(2.5, 2.5),
    )
    assert result["version"] == VERSION
    assert result["version"] == "cecchino_goal_intensity_v2"
