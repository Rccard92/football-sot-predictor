"""Test builder component_trace e error_direction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.v31_component_error_direction import (
    compute_error_direction,
    compute_suspicion_level,
)
from app.services.backtest.v31_component_trace_builder import flatten_component_rows


def test_error_direction_overestimated():
    assert (
        compute_error_direction(
            match_error=-2.0,
            predicted_value=5.0,
            actual_value=3.0,
            delta=-2.0,
            comparison_type="direct",
        )
        == "overestimated"
    )


def test_error_direction_not_comparable_diagnostic():
    assert (
        compute_error_direction(
            match_error=2.0,
            predicted_value=1.0,
            actual_value=None,
            delta=None,
            comparison_type="diagnostic_only",
        )
        == "not_comparable"
    )


def test_suspicion_high():
    assert (
        compute_suspicion_level(
            error_direction="underestimated",
            match_error=3.0,
            delta_pct=30.0,
        )
        == "high"
    )


def test_flatten_component_rows():
    payload = {
        "match_summary": {
            "fixture_id": 1,
            "round_number": 5,
            "match": "A vs B",
            "strategy_key": "v31_equal_weights",
        },
        "home": {
            "team_name": "A",
            "inputs": [
                {
                    "key": "avg_sot_for",
                    "label": "SOT",
                    "macro_area": "offensive_production",
                    "predicted_value": 4.0,
                    "actual_value": 5.0,
                    "error_direction": "underestimated",
                    "actual_comparison_type": "direct",
                },
            ],
        },
        "away": {"team_name": "B", "inputs": []},
        "match_level": {
            "inputs": [
                {
                    "key": "boost_applied",
                    "label": "Boost",
                    "macro_area": "match_dynamics",
                    "predicted_value": 0.1,
                    "error_direction": "not_comparable",
                    "actual_comparison_type": "diagnostic_only",
                },
            ],
        },
    }
    rows = flatten_component_rows(payload)
    assert len(rows) == 2
    assert rows[0]["team_side"] == "home"
    assert rows[1]["team_side"] == "match"
    assert rows[1]["error_direction"] == "not_comparable"


@patch("app.services.backtest.v31_component_trace_builder.resolve_actual_component_value")
@patch("app.services.backtest.v31_component_trace_builder.extract_fixture_signals")
def test_build_component_comparison_mock(mock_signals, mock_resolve):
    from app.services.backtest.v31_component_trace_builder import build_component_comparison

    mock_resolve.return_value = MagicMock(
        value=5.0,
        source="fixture_team_stats.shots_on_target",
        status="available",
        actual_comparison_type="direct",
    )
    home = MagicMock()
    home.team_raw = {"sample_count": 10}
    home.macros = {"recent_form_index": 1.05}
    away = MagicMock()
    away.team_raw = {"sample_count": 8}
    away.macros = {}
    sig = MagicMock()
    sig.home = home
    sig.away = away
    mock_signals.return_value = sig

    dataset_row = {
        "metadata": {
            "fixture_id": 99,
            "round_number": 3,
            "home_team_id": 1,
            "away_team_id": 2,
            "home_team_name": "Home",
            "away_team_name": "Away",
        },
    }
    simulated = {
        "fixture_id": 99,
        "predicted_total_sot": 9.0,
        "actual_total_sot": 11.0,
        "error": 2.0,
        "trace": {
            "home_base_trace": {
                "components": {
                    "avg_sot_for": 4.5,
                    "opponent_conceded_sot_avg": 3.2,
                    "last5_avg_sot_for": 4.0,
                    "home_away_split_sot_for": 4.2,
                    "xg_to_sot": 0.25,
                    "shots_to_sot": 0.4,
                },
                "base_weights_used": {
                    "avg_sot_for": 0.3,
                    "opponent_conceded_sot_avg": 0.2,
                    "last5_avg_sot_for": 0.15,
                    "home_away_split_sot_for": 0.1,
                    "xg_to_sot": 0.15,
                    "shots_to_sot": 0.1,
                },
            },
            "away_base_trace": {
                "components": {},
                "base_weights_used": {},
            },
            "home_context_weights": {"recent_form_index": 1.0},
            "away_context_weights": {},
            "high_total_signal": 0.5,
        },
    }
    db = MagicMock()
    out = build_component_comparison(
        db,
        dataset_row=dataset_row,
        simulated_row=simulated,
        strategy_key="v31_equal_weights",
    )
    assert out is not None
    assert out["match_summary"]["error_type"] == "understated"
    assert len(out["home"]["inputs"]) >= 1
