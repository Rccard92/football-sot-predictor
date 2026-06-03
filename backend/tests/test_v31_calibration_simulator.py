"""Test unit simulatore calibrazione v3.1."""

from __future__ import annotations

from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_metrics import (
    regression_metrics,
    walk_forward_metrics,
)
from app.services.backtest.v31_calibration_simulator_strategies import (
    STRATEGY_KEYS,
    simulate_row,
)


def _macro_side(off: float = 1.05) -> dict:
    return {
        "offensive_production_index": off,
        "opponent_defensive_resistance_index": 1.0,
        "recent_form_index": 1.02,
        "chance_quality_index": 1.03,
        "pace_control_index": 1.0,
        "home_away_split_index": 1.01,
        "player_layer_index": 1.0,
        "injuries_unavailable_index": 0.98,
        "lineups_index": 1.0,
        "weighted_macro_multiplier": 1.0,
    }


def _sample_row(*, round_number: int = 10, actual: int = 9) -> dict:
    return {
        "metadata": {
            "fixture_id": 100 + round_number,
            "round_number": round_number,
            "home_team_name": "Alpha",
            "away_team_name": "Beta",
        },
        "target": {
            "actual_total_sot": actual,
            "actual_home_sot": 5,
            "actual_away_sot": 4,
        },
        "features": {
            "team_raw_features": {
                "home": {"avg_sot_for": 3.5},
                "away": {"avg_sot_for": 3.2},
            },
            "existing_macro_features": {
                "home": _macro_side(),
                "away": _macro_side(1.04),
            },
            "player_layer": {"home": {}, "away": {}},
            "lineups": {"home": {}, "away": {}},
            "unavailable": {"home": {}, "away": {}},
            "data_quality": {
                "team_stats_status": "ok",
                "warning_count": 0,
            },
            "league_context": {"round_number": round_number},
        },
        "comparisons": {
            "v2_1_predicted_total": 8.0,
            "allowed_for_v31_training": False,
        },
    }


def test_extract_signals_ignores_comparisons_and_target():
    row = _sample_row()
    sig = extract_fixture_signals(row)
    assert sig is not None
    assert sig.home.baseline_sot == 3.5
    assert sig.fixture_id == 110


def test_simulate_row_produces_prediction_and_no_legacy_features():
    row = _sample_row()
    sim = simulate_row(row, "v31_equal_weights")
    assert sim is not None
    assert sim["predicted_total_sot"] is not None
    assert float(sim["predicted_total_sot"]) > 4.0
    assert "estimated_probability_over_6_5" in sim
    assert sim["decision"] in ("GIOCA", "NO_BET", "BORDERLINE")
    assert sim["human_explanation"]
    assert sim["trace"]["macro_weights"]


def test_conservative_fewer_picks_than_balanced():
    rows = [_sample_row(round_number=r) for r in range(5, 20)]
    cons = [simulate_row(r, "v31_conservative_selector") for r in rows]
    bal = [simulate_row(r, "v31_balanced_selector") for r in rows]
    cons_picks = sum(1 for s in cons if s and s["decision"] == "GIOCA")
    bal_picks = sum(1 for s in bal if s and s["decision"] == "GIOCA")
    assert cons_picks <= bal_picks


def test_regression_mae_on_synthetic():
    rows = []
    for r in range(5, 18):
        sim = simulate_row(_sample_row(round_number=r, actual=8), "v31_core_sot_xg")
        assert sim
        rows.append(sim)
    reg = regression_metrics(rows)
    assert reg["mae"] is not None
    assert reg["n"] == len(rows)


def test_walk_forward_splits():
    rows = []
    for r in range(5, 38):
        sim = simulate_row(_sample_row(round_number=r), "v31_equal_weights")
        if sim:
            rows.append(sim)
    wf = walk_forward_metrics(rows)
    assert "wf_5_15_to_16_26" in wf
    assert wf["wf_5_15_to_16_26"]["test_fixture_count"] > 0


def test_all_strategy_keys_simulate():
    row = _sample_row()
    for key in STRATEGY_KEYS:
        assert simulate_row(row, key) is not None
