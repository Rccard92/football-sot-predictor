"""Test unit simulatore calibrazione v3.1."""

from __future__ import annotations

from app.services.backtest.v31_calibration_simulator_base_sot import (
    absolute_from_field,
    calculate_team_base_sot,
)
from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_metrics import (
    compute_best_by,
    prediction_diagnostics,
    regression_metrics,
    walk_forward_metrics,
)
from app.services.backtest.v31_calibration_simulator_predictor import prob_over_line
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


def _sample_row(
    *,
    round_number: int = 10,
    actual: int = 9,
    avg_sot_for: float = 1.05,
    use_absolute_sot: bool = False,
) -> dict:
    if use_absolute_sot:
        home_team = {
            "avg_sot_for": 3.5,
            "avg_sot_against": 3.2,
            "last5_avg_sot_for": 3.4,
            "home_away_split_sot_for": 3.6,
            "avg_xg_for": 1.3,
            "avg_total_shots_for": 12.0,
        }
        away_team = {
            "avg_sot_for": 3.2,
            "avg_sot_against": 3.5,
            "last5_avg_sot_for": 3.1,
            "home_away_split_sot_for": 3.0,
            "avg_xg_for": 1.2,
            "avg_total_shots_for": 11.0,
        }
    else:
        home_team = {
            "avg_sot_for": avg_sot_for,
            "avg_sot_against": 1.0,
            "last5_avg_sot_for": avg_sot_for,
            "home_away_split_sot_for": avg_sot_for,
            "avg_xg_for": 1.03,
        }
        away_team = {
            "avg_sot_for": avg_sot_for - 0.02,
            "avg_sot_against": 1.0,
            "last5_avg_sot_for": avg_sot_for,
            "home_away_split_sot_for": avg_sot_for,
            "avg_xg_for": 1.02,
        }

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
            "team_raw_features": {"home": home_team, "away": away_team},
            "existing_macro_features": {
                "home": _macro_side(),
                "away": _macro_side(1.04),
            },
            "player_layer": {
                "home": {"player_layer_index_existing": 1.0, "starting_xi_available": True},
                "away": {"player_layer_index_existing": 1.0, "starting_xi_available": True},
            },
            "lineups": {
                "home": {"lineup_available": True},
                "away": {"lineup_available": True},
            },
            "unavailable": {"home": {}, "away": {}},
            "data_quality": {
                "team_stats_status": "ok",
                "warning_count": 0,
                "fallback_count": 0,
                "lineup_status": "ok",
                "player_layer_status": "ok",
                "unavailable_status": "ok",
            },
            "league_context": {"round_number": round_number},
        },
        "comparisons": {
            "v2_1_predicted_total": 8.0,
            "allowed_for_v31_training": False,
        },
    }


def test_absolute_from_field_macro_index():
    missing: list[str] = []
    v = absolute_from_field(1.05, 3.35, "test", missing)
    assert v is not None
    assert 3.0 < v < 4.0
    assert not missing


def test_calculate_team_base_sot_realistic():
    side = {
        "avg_sot_for": 3.5,
        "last5_avg_sot_for": 3.4,
        "home_away_split_sot_for": 3.6,
        "avg_xg_for": 1.3,
        "avg_total_shots_for": 12.0,
    }
    opp = {"avg_sot_against": 3.2}
    base, trace = calculate_team_base_sot(side, opp, {})
    assert base is not None
    assert 2.5 <= base <= 6.5


def test_prob_over_65_high_when_mu_8():
    p = prob_over_line(8.0, 6.5)
    assert p >= 0.7


def test_simulate_row_realistic_total_from_macro_indices():
    row = _sample_row()
    sim = simulate_row(row, "v31_balanced_selector")
    assert sim is not None
    total = float(sim["predicted_total_sot"])
    assert 5.0 <= total <= 11.0


def test_macro_index_and_absolute_similar_scale():
    r_idx = _sample_row(avg_sot_for=1.05, use_absolute_sot=False)
    r_abs = _sample_row(use_absolute_sot=True)
    t_idx = float(simulate_row(r_idx, "v31_context_adjusted")["predicted_total_sot"])
    t_abs = float(simulate_row(r_abs, "v31_context_adjusted")["predicted_total_sot"])
    assert abs(t_idx - t_abs) < 2.5


def test_balanced_selector_has_picks_on_batch():
    rows = [_sample_row(round_number=r, actual=8 + (r % 3)) for r in range(5, 20)]
    simulated = [simulate_row(r, "v31_balanced_selector") for r in rows]
    picks = sum(1 for s in simulated if s and s["decision"] == "GIOCA")
    assert picks > 0


def test_prediction_diagnostics_no_scale_warning_on_normal_batch():
    rows = [simulate_row(_sample_row(round_number=r), "v31_balanced_selector") for r in range(5, 20)]
    rows = [r for r in rows if r]
    diag = prediction_diagnostics(rows)
    assert diag["predicted_total_avg"] is not None
    assert 6.5 <= diag["predicted_total_avg"] <= 9.5
    assert diag["scale_warning"] is False


def test_compute_best_by_skips_zero_pick_for_recommendation():
    blocks = [
        {"key": "a", "metrics": {"pick_count": 0, "hit_rate": None, "mae": 1.0}},
        {
            "key": "b",
            "metrics": {"pick_count": 10, "hit_rate": 55.0, "mae": 2.5},
            "prediction_diagnostics": {"scale_warning": False},
        },
    ]
    best = compute_best_by(blocks)
    assert best["recommended_strategy"] == "b"
    assert best["hit_rate"]["strategy"] == "b"


def test_regression_mae_not_extreme_bias():
    rows = [simulate_row(_sample_row(round_number=r), "v31_equal_weights") for r in range(5, 18)]
    rows = [r for r in rows if r]
    reg = regression_metrics(rows)
    assert reg["bias"] is not None
    assert abs(float(reg["bias"])) < 4.0


def test_walk_forward_splits():
    rows = []
    for r in range(5, 38):
        sim = simulate_row(_sample_row(round_number=r), "v31_equal_weights")
        if sim:
            rows.append(sim)
    wf = walk_forward_metrics(rows)
    assert wf["wf_5_15_to_16_26"]["test_fixture_count"] > 0


def test_all_strategy_keys_simulate():
    row = _sample_row()
    for key in STRATEGY_KEYS:
        assert simulate_row(row, key) is not None
