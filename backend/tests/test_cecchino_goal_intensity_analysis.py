"""Test Intensità Goal — Cecchino Fase 49 (v4 Goal Attesi)."""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    STATUS_AVAILABLE,
    VERSION,
    _classify_expected_goals,
    _poisson_prob_over_line,
    build_cecchino_goal_intensity_analysis_from_expected_goals,
)


@pytest.mark.parametrize(
    ("eg", "expected_key", "expected_label"),
    [
        (0.49, "very_defensive", "Molto Difensiva"),
        (0.50, "defensive", "Difensiva"),
        (1.49, "defensive", "Difensiva"),
        (1.50, "balanced", "Equilibrata"),
        (2.49, "balanced", "Equilibrata"),
        (2.50, "offensive", "Offensiva"),
        (3.49, "offensive", "Offensiva"),
        (3.50, "very_offensive", "Molto Offensiva"),
    ],
)
def test_classification_thresholds(eg: float, expected_key: str, expected_label: str):
    key, label = _classify_expected_goals(eg)
    assert key == expected_key
    assert label == expected_label


@pytest.mark.parametrize(
    ("eg", "active_keys"),
    [
        (0.49, []),
        (0.50, ["over_0_5"]),
        (1.49, ["over_0_5"]),
        (1.50, ["over_0_5", "over_1_5"]),
        (2.49, ["over_0_5", "over_1_5"]),
        (2.50, ["over_0_5", "over_1_5", "over_2_5"]),
        (3.49, ["over_0_5", "over_1_5", "over_2_5"]),
        (3.50, ["over_0_5", "over_1_5", "over_2_5", "over_3_5"]),
    ],
)
def test_active_thresholds(eg: float, active_keys: list[str]):
    result = build_cecchino_goal_intensity_analysis_from_expected_goals(eg)
    thresholds = result["thresholds"]
    for key in ("over_0_5", "over_1_5", "over_2_5", "over_3_5"):
        assert thresholds[key]["active"] == (key in active_keys)
    assert result["active_thresholds_count"] == len(active_keys)


def test_poisson_probabilities_monotonic():
    lam = 2.5
    p05 = _poisson_prob_over_line(lam, 0.5)
    p15 = _poisson_prob_over_line(lam, 1.5)
    p25 = _poisson_prob_over_line(lam, 2.5)
    p35 = _poisson_prob_over_line(lam, 3.5)
    assert p05 > p15 > p25 > p35

    result = build_cecchino_goal_intensity_analysis_from_expected_goals(lam)
    th = result["thresholds"]
    assert th["over_0_5"]["probability"] > th["over_1_5"]["probability"]
    assert th["over_1_5"]["probability"] > th["over_2_5"]["probability"]
    assert th["over_2_5"]["probability"] > th["over_3_5"]["probability"]


def test_insufficient_data_when_expected_goals_null():
    result = build_cecchino_goal_intensity_analysis_from_expected_goals(None)
    assert result["status"] == STATUS_INSUFFICIENT_DATA
    assert result["expected_goals_total"] is None
    assert result["thresholds"] is None
    assert result["final_label"] == "Dati insufficienti"
    assert "missing_internal_expected_goals_total" in result["warnings"]


def test_available_payload_structure():
    result = build_cecchino_goal_intensity_analysis_from_expected_goals(2.72)
    assert result["status"] == STATUS_AVAILABLE
    assert result["version"] == VERSION
    assert result["method"] == "expected_goals_thresholds"
    assert result["expected_goals_total"] == pytest.approx(2.72)
    assert result["final_class_key"] == "offensive"
    assert result["debug"]["source"] == "internal_cecchino_goal_engine"
    assert "thresholds" in result
    assert result["plain_summary"]


def test_independence_from_other_modules():
    mod = importlib.import_module("app.services.cecchino.cecchino_goal_intensity_analysis")
    source = inspect.getsource(mod)
    assert "cecchino_balance_analysis" not in source
    assert "cecchino_icm_analysis" not in source
    assert "team_sot_predictions" not in source
    assert "build_cecchino_balance_analysis" not in source


def test_version_v4():
    result = build_cecchino_goal_intensity_analysis_from_expected_goals(2.0)
    assert result["version"] == "cecchino_goal_intensity_v4_expected_goals"
