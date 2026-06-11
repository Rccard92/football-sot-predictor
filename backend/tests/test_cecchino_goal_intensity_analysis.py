"""Test Intensità Goal — Cecchino Fase 48 (v3 OVER-only)."""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_BASELINE,
    VERSION,
    _classify_over_percentile,
    build_cecchino_goal_intensity_analysis_from_parity,
)
from app.services.cecchino.cecchino_goal_intensity_baselines import percentile_rank_percent


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


def _over_baseline(
    over_values: list[float],
    *,
    source: str = "league",
    sample: int | None = None,
) -> dict:
    from app.services.cecchino.cecchino_goal_intensity_baselines import _over_distribution

    dist = _over_distribution(over_values)
    return {
        "source": source,
        "sample_size": sample if sample is not None else len(over_values),
        "method": "percentile_distribution",
        "over_values": over_values,
        **dist,
    }


def test_raw_over_q44_from_spec():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under = _ft_parity(_blocks(2, 2, 1, 1))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under,
        over_baseline=_over_baseline([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
    )

    assert result["status"] == STATUS_AVAILABLE
    assert result["raw"]["over_q44"] == pytest.approx(5.0)
    assert result["raw"]["under_q44_deprecated"] == pytest.approx(3.0)


def test_percentile_rank_proportion_leq():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_rank_percent(values, 4.0) == pytest.approx(80.0)


@pytest.mark.parametrize(
    ("percentile", "expected_key", "expected_label"),
    [
        (19.9, "very_defensive", "Molto Difensiva"),
        (20.0, "defensive", "Difensiva"),
        (39.9, "defensive", "Difensiva"),
        (40.0, "balanced", "Equilibrata"),
        (60.0, "balanced", "Equilibrata"),
        (60.1, "offensive", "Offensiva"),
        (80.0, "offensive", "Offensiva"),
        (80.1, "very_offensive", "Molto Offensiva"),
    ],
)
def test_percentile_thresholds(percentile: float, expected_key: str, expected_label: str):
    key, label = _classify_over_percentile(percentile)
    assert key == expected_key
    assert label == expected_label


def test_index_vs_median():
    over = _ft_parity(_blocks(1.2, 1.2, 1.2, 1.2))  # raw over = 2.4
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        over_baseline=_over_baseline([1.0, 2.0, 2.0, 3.0]),
    )

    assert result["raw"]["over_q44"] == pytest.approx(2.4)
    assert result["over_analysis"]["over_index_vs_median"] == pytest.approx(1.20)


def test_insufficient_baseline_when_baseline_null():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        over_baseline={
            "source": None,
            "sample_size": 0,
            "median_over_q44": None,
            "over_values": [],
            "method": "percentile_distribution",
        },
    )

    assert result["status"] == STATUS_INSUFFICIENT_BASELINE
    assert result["over_analysis"] is None
    assert result["final_label"] == "Baseline insufficiente"
    assert "insufficient_goal_intensity_over_baseline" in result["warnings"]
    assert result["raw"]["over_q44"] == pytest.approx(5.0)


def test_missing_over_sources_insufficient_data():
    over = {"status": STATUS_INSUFFICIENT_DATA, "blocks": None}
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        over_baseline=_over_baseline([1.0, 2.0, 3.0]),
    )

    assert result["status"] == STATUS_INSUFFICIENT_DATA
    assert result["raw"] is None
    assert result["final_label"] == "Dati insufficienti"


def test_under_independence():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    under_low = _ft_parity(_blocks(1, 1, 1, 1))
    under_high = _ft_parity(_blocks(5, 5, 5, 5))
    baseline = _over_baseline([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    result_low = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under_low,
        over_baseline=baseline,
    )
    result_high = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        under_ft=under_high,
        over_baseline=baseline,
    )

    assert result_low["final_label"] == result_high["final_label"]
    assert result_low["final_class_key"] == result_high["final_class_key"]
    assert result_low["over_analysis"] == result_high["over_analysis"]


def test_independence_from_balance_analysis():
    mod = importlib.import_module("app.services.cecchino.cecchino_goal_intensity_analysis")
    source = inspect.getsource(mod)
    assert "cecchino_balance_analysis" not in source
    assert "build_cecchino_balance_analysis" not in source


def test_version_v3():
    over = _ft_parity(_blocks(2, 4, 1, 3))
    result = build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over,
        over_baseline=_over_baseline([1.0, 2.0, 3.0, 4.0, 5.0]),
    )
    assert result["version"] == VERSION
    assert result["version"] == "cecchino_goal_intensity_v3_over_only"
    assert result["method"] == "over_percentile"
