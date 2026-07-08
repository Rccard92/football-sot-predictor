"""Test risoluzione quota Under 2.5 per formula D39."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_selection_keys import SEL_UNDER_2_5
from app.services.cecchino.cecchino_signal_backfill import _rebuild_signals_matrix_on_row
from app.services.cecchino.cecchino_signal_goal_refs import (
    rebuild_signals_matrix_for_output,
    resolve_under_2_5_cecchino_odd,
    resolve_under_2_5_cecchino_odd_from_fixture,
)
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def _signals_excel_d(matrix: dict, key: str = "under_under_pt") -> str:
    for row in matrix["rows"]:
        if row["key"] == key:
            return row["signals"]["excel_d"]
    raise KeyError(key)


def test_resolve_under_odd_from_kpi_panel():
    kpi = {
        "rows": [
            {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "segno": "Under 2.5"},
        ],
    }
    assert resolve_under_2_5_cecchino_odd(kpi_panel=kpi) == 1.85


def test_resolve_under_odd_kpi_label_fallback():
    kpi = {
        "rows": [
            {"segno": "Under 2.5", "quota_cecchino": 1.92},
        ],
    }
    assert resolve_under_2_5_cecchino_odd(kpi_panel=kpi) == 1.92


def test_resolve_under_odd_from_goal_markets():
    goal_markets = {
        SEL_UNDER_2_5: {"final_odd": 1.75, "status": "available", "formula_version": "v1"},
    }
    assert resolve_under_2_5_cecchino_odd(goal_markets=goal_markets) == 1.75


def test_resolve_under_odd_kpi_priority_over_goal_markets():
    kpi = {"rows": [{"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.80}]}
    goal_markets = {SEL_UNDER_2_5: {"final_odd": 2.10}}
    assert resolve_under_2_5_cecchino_odd(kpi_panel=kpi, goal_markets=goal_markets) == 1.80


def test_resolve_under_odd_from_fixture():
    row = SimpleNamespace(
        kpi_panel_json={"rows": [{"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.65}]},
        cecchino_output_json={"goal_markets": {SEL_UNDER_2_5: {"final_odd": 1.90}}},
    )
    assert resolve_under_2_5_cecchino_odd_from_fixture(row) == 1.65


def test_rebuild_signals_matrix_for_output_with_goal_markets():
    output = {
        "final": {
            "status": "available",
            "quota_1": 2.30,
            "quota_x": 3.20,
            "quota_2": 2.00,
            "prob_1": 0.40,
            "prob_x": 0.30,
            "prob_2": 0.30,
        },
        "goal_markets": {SEL_UNDER_2_5: {"final_odd": 1.80}},
    }
    matrix = rebuild_signals_matrix_for_output(output, sample_home_away_split=12)
    assert matrix is not None
    assert _signals_excel_d(matrix) == "SI"
    assert matrix["inputs"]["under_2_5_cecchino_odd"] == 1.80


def test_rebuild_signals_matrix_on_row_passes_under_odd():
    row = SimpleNamespace(
        stats_snapshot_json={"home_away": {"home_sample_count": 8, "away_sample_count": 8}},
        kpi_panel_json={"rows": [{"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.80}]},
        cecchino_output_json={
            "final": {
                "status": "available",
                "quota_1": 2.30,
                "quota_x": 3.20,
                "quota_2": 2.00,
            },
            "signals_matrix": build_signals_matrix(
                q1=2.30,
                qx=3.20,
                q2=2.00,
                sample_home_away_split=16,
            ),
        },
    )
    assert _rebuild_signals_matrix_on_row(row) is True
    matrix = row.cecchino_output_json["signals_matrix"]
    assert _signals_excel_d(matrix) == "SI"
    assert matrix["inputs"]["under_2_5_cecchino_odd"] == 1.80
