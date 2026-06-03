"""Boost e aggiustamenti dinamici per strategie aggressive v3.1."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_cohort import CohortStats, get_interactions
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _xi_compromised(macros: dict[str, float | None], player_layer: dict[str, Any], side: str) -> bool:
    pl = _f(macros.get("player_layer_index"))
    inj = _f(macros.get("injuries_unavailable_index"))
    side_pl = player_layer.get(side) if isinstance(player_layer, dict) else {}
    if not isinstance(side_pl, dict):
        side_pl = {}
    xi = side_pl.get("starting_xi_available")
    return (pl is not None and pl < 0.92) or (inj is not None and inj < 0.95) or xi is False


def dynamics_variance_unlocked(
    signals: FixtureSignals,
    inter: dict[str, Any],
    _cohort: CohortStats | None,
) -> dict[str, Any]:
    open_s = float(inter.get("match_open_score") or 2.0)
    mult = 1.0 + min(0.25, (open_s - 2.0) * 0.08)
    return {
        "home_side_multiplier": mult,
        "away_side_multiplier": mult,
        "total_boost": min(1.2, (open_s - 2.0) * 0.35),
        "boost_reason": "variance_unlocked_match_open",
    }


def dynamics_big_match_boost(
    signals: FixtureSignals,
    inter: dict[str, Any],
    cohort: CohortStats | None,
) -> dict[str, Any]:
    c = cohort or CohortStats()
    h = float(inter.get("home_offensive_strength") or 0)
    a = float(inter.get("away_offensive_strength") or 0)
    boost = 0.0
    reason = "no_big_match_signal"
    if h >= c.offensive_p75 and a >= c.offensive_p75:
        boost = 1.2
        reason = "both_offensive_p75"
    elif h >= c.offensive_p65 and a >= c.offensive_p65:
        boost = 0.8
        reason = "both_offensive_p65"
    if _xi_compromised(signals.home.macros, signals.player_layer, "home"):
        boost *= 0.6
        reason += "_home_xi_reduced"
    if _xi_compromised(signals.away.macros, signals.player_layer, "away"):
        boost *= 0.6
        reason += "_away_xi_reduced"
    return {
        "home_side_multiplier": 1.0,
        "away_side_multiplier": 1.0,
        "total_boost": boost,
        "boost_reason": reason,
    }


def dynamics_big_vs_weak_push(
    signals: FixtureSignals,
    inter: dict[str, Any],
    cohort: CohortStats | None,
) -> dict[str, Any]:
    h_att = float(inter.get("home_attack_vs_away_defense") or 1.0)
    a_att = float(inter.get("away_attack_vs_home_defense") or 1.0)
    h_weak = float(inter.get("away_defensive_weakness_faced") or 0)
    a_weak = float(inter.get("home_defensive_weakness_faced") or 0)
    home_mult = 1.0
    away_mult = 1.0
    boost = 0.0
    reason = "neutral"
    if h_att >= a_att and h_att >= 1.15 and h_weak >= 3.5:
        home_mult = 1.0 + min(0.35, (h_att - 1.0) * 0.25)
        boost = min(1.5, (h_att - 1.0) * 0.8)
        reason = "home_favorite_vs_weak_defense"
    elif a_att > h_att and a_att >= 1.15 and a_weak >= 3.5:
        away_mult = 1.0 + min(0.35, (a_att - 1.0) * 0.25)
        boost = min(1.5, (a_att - 1.0) * 0.8)
        reason = "away_favorite_vs_weak_defense"
    return {
        "home_side_multiplier": home_mult,
        "away_side_multiplier": away_mult,
        "total_boost": boost * 0.5,
        "boost_reason": reason,
    }


def dynamics_chaos_game(
    signals: FixtureSignals,
    inter: dict[str, Any],
    cohort: CohortStats | None,
) -> dict[str, Any]:
    c = cohort or CohortStats()
    open_s = float(inter.get("match_open_score") or 0)
    pace = float(inter.get("pace_avg") or 1.0)
    comb = float(inter.get("combined_offensive_strength") or 0)
    boost = 0.0
    if open_s >= c.match_open_p70 and pace >= 1.02 and comb >= c.combined_offensive_p65:
        boost = min(2.0, 0.6 + (open_s - c.match_open_p70) * 0.5)
    return {
        "home_side_multiplier": 1.0 + min(0.12, boost * 0.05),
        "away_side_multiplier": 1.0 + min(0.12, boost * 0.05),
        "total_boost": boost,
        "boost_reason": "chaos_open_game" if boost > 0 else "chaos_neutral",
    }


def dynamics_low_block_guard(
    signals: FixtureSignals,
    inter: dict[str, Any],
    _cohort: CohortStats | None,
) -> dict[str, Any]:
    pace = float(inter.get("pace_avg") or 1.0)
    comb_xg = float(inter.get("combined_xg_strength") or 0)
    fav = float(inter.get("favorite_pressure_score") or 1.0)
    penalty = 0.0
    if pace < 0.98 and comb_xg < 2.4 and fav >= 1.2:
        penalty = min(1.2, (1.0 - pace) * 2.0 + 0.3)
    return {
        "home_side_multiplier": 1.0,
        "away_side_multiplier": 1.0,
        "total_boost": -penalty,
        "boost_reason": "low_block_penalty" if penalty > 0 else "no_penalty",
    }


def _classify_bucket_profile(inter: dict[str, Any], cohort: CohortStats | None) -> str:
    c = cohort or CohortStats()
    comb = float(inter.get("combined_offensive_strength") or 0)
    open_s = float(inter.get("match_open_score") or 0)
    if comb >= c.combined_offensive_p75 and open_s >= c.match_open_p70:
        return "very_high_total"
    if comb >= c.combined_offensive_p65 or open_s >= c.match_open_p70:
        return "high_total"
    if comb < c.combined_offensive_p65 * 0.85 and open_s < 1.8:
        return "low_total"
    return "normal_total"


def dynamics_extreme_bucket_model(
    signals: FixtureSignals,
    inter: dict[str, Any],
    cohort: CohortStats | None,
) -> dict[str, Any]:
    """Override totale via bucket sperimentale."""
    bucket = _classify_bucket_profile(inter, cohort)
    targets = {
        "low_total": 5.7,
        "normal_total": 7.6,
        "high_total": 10.0,
        "very_high_total": 11.5,
    }
    return {
        "home_side_multiplier": 1.0,
        "away_side_multiplier": 1.0,
        "total_boost": 0.0,
        "boost_reason": f"extreme_bucket_{bucket}",
        "bucket_override_total": targets.get(bucket, 7.6),
        "profile_bucket": bucket,
    }


DYNAMICS_HANDLERS: dict[str, Any] = {
    "v31_variance_unlocked": dynamics_variance_unlocked,
    "v31_big_match_boost": dynamics_big_match_boost,
    "v31_big_vs_weak_push": dynamics_big_vs_weak_push,
    "v31_chaos_game": dynamics_chaos_game,
    "v31_low_block_guard": dynamics_low_block_guard,
    "v31_extreme_bucket_model": dynamics_extreme_bucket_model,
}


def apply_dynamics(
    strategy_key: str,
    signals: FixtureSignals,
    cohort: CohortStats | None,
) -> dict[str, Any]:
    handler = DYNAMICS_HANDLERS.get(strategy_key)
    inter = get_interactions(signals, cohort)
    if handler is None:
        return {"interaction_scores": inter}
    dyn = handler(signals, inter, cohort)
    dyn["interaction_scores"] = inter
    return dyn
