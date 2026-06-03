"""Interaction features pre-match per simulatore v3.1 (no leakage)."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_base_sot import (
    LEAGUE_AVG_SOT_FOR,
    LEAGUE_AVG_SHOTS_FOR,
    LEAGUE_AVG_XG_FOR,
    absolute_from_field,
    league_avgs,
)
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _abs_metric(
    team_raw: dict[str, Any],
    key: str,
    league_avg: float,
    missing: list[str],
) -> float | None:
    return absolute_from_field(team_raw.get(key), league_avg, key, missing)


def side_strength(
    team_raw: dict[str, Any],
    macros: dict[str, float | None],
    league_context: dict[str, Any] | None,
) -> dict[str, float | None]:
    league_sot, league_xg, league_shots = league_avgs(league_context)
    missing: list[str] = []
    sot = _abs_metric(team_raw, "avg_sot_for", league_sot, missing)
    xg = _abs_metric(team_raw, "avg_xg_for", league_xg, missing)
    shots = _abs_metric(team_raw, "avg_total_shots_for", league_shots, missing)
    off_macro = _f(macros.get("offensive_production_index"))
    player = _f(macros.get("player_layer_index"))
    parts = [p for p in (sot, xg, shots) if p is not None]
    offensive = (sum(parts) / len(parts)) if parts else None
    if offensive is not None and off_macro is not None:
        offensive = 0.7 * offensive + 0.3 * off_macro * league_sot
    elif offensive is None and off_macro is not None:
        offensive = off_macro * league_sot
    return {
        "offensive_strength": offensive,
        "sot_strength": sot,
        "xg_strength": xg,
        "shot_volume_strength": shots,
        "player_layer_index": player,
    }


def opponent_defensive_weakness(
    opp_raw: dict[str, Any],
    macros: dict[str, float | None],
    league_context: dict[str, Any] | None,
) -> float | None:
    league_sot, _, league_shots = league_avgs(league_context)
    missing: list[str] = []
    conceded = _abs_metric(opp_raw, "avg_sot_against", league_sot, missing)
    if conceded is None:
        conceded = _abs_metric(opp_raw, "avg_sot_for", league_sot, missing)
    resist = _f(macros.get("opponent_defensive_resistance_index"))
    if conceded is not None and resist is not None:
        return 0.6 * conceded + 0.4 * (2.0 - resist) * league_sot
    return conceded


def compute_fixture_interactions(signals: FixtureSignals) -> dict[str, Any]:
    lc = signals.league_context
    home_str = side_strength(signals.home.team_raw, signals.home.macros, lc)
    away_str = side_strength(signals.away.team_raw, signals.away.macros, lc)
    home_vs_away_def = opponent_defensive_weakness(
        signals.away.team_raw,
        signals.away.macros,
        lc,
    )
    away_vs_home_def = opponent_defensive_weakness(
        signals.home.team_raw,
        signals.home.macros,
        lc,
    )

    h_off = home_str.get("offensive_strength") or LEAGUE_AVG_SOT_FOR
    a_off = away_str.get("offensive_strength") or LEAGUE_AVG_SOT_FOR
    h_xg = home_str.get("xg_strength") or LEAGUE_AVG_XG_FOR
    a_xg = away_str.get("xg_strength") or LEAGUE_AVG_XG_FOR
    h_sh = home_str.get("shot_volume_strength") or LEAGUE_AVG_SHOTS_FOR
    a_sh = away_str.get("shot_volume_strength") or LEAGUE_AVG_SHOTS_FOR

    home_attack_vs_def = (h_off * (home_vs_away_def or LEAGUE_AVG_SOT_FOR)) / LEAGUE_AVG_SOT_FOR
    away_attack_vs_def = (a_off * (away_vs_home_def or LEAGUE_AVG_SOT_FOR)) / LEAGUE_AVG_SOT_FOR

    home_xg_vol = (h_xg * h_sh) / (LEAGUE_AVG_XG_FOR * LEAGUE_AVG_SHOTS_FOR)
    away_xg_vol = (a_xg * a_sh) / (LEAGUE_AVG_XG_FOR * LEAGUE_AVG_SHOTS_FOR)

    h_pl = home_str.get("player_layer_index") or 1.0
    a_pl = away_str.get("player_layer_index") or 1.0
    home_lineup_attack = h_pl * h_off / LEAGUE_AVG_SOT_FOR
    away_lineup_attack = a_pl * a_off / LEAGUE_AVG_SOT_FOR

    h_inj = _f(signals.home.macros.get("injuries_unavailable_index")) or 1.0
    absence_home = max(0.0, (1.05 - h_inj)) * h_off / LEAGUE_AVG_SOT_FOR

    match_open = home_attack_vs_def + away_attack_vs_def
    favorite_pressure = max(home_attack_vs_def, away_attack_vs_def)

    combined_offensive = h_off + a_off
    combined_xg = h_xg + a_xg
    combined_sot = (home_str.get("sot_strength") or 0) + (away_str.get("sot_strength") or 0)

    pace = (
        (_f(signals.home.macros.get("pace_control_index")) or 1.0)
        + (_f(signals.away.macros.get("pace_control_index")) or 1.0)
    ) / 2.0

    return {
        "home_offensive_strength": round(h_off, 4),
        "away_offensive_strength": round(a_off, 4),
        "combined_offensive_strength": round(combined_offensive, 4),
        "combined_xg_strength": round(combined_xg, 4),
        "combined_sot_strength": round(combined_sot, 4),
        "home_attack_vs_away_defense": round(home_attack_vs_def, 4),
        "away_attack_vs_home_defense": round(away_attack_vs_def, 4),
        "attack_vs_defense_interaction_home": round(home_attack_vs_def, 4),
        "attack_vs_defense_interaction_away": round(away_attack_vs_def, 4),
        "xg_volume_interaction_home": round(home_xg_vol, 4),
        "xg_volume_interaction_away": round(away_xg_vol, 4),
        "lineup_attack_interaction_home": round(home_lineup_attack, 4),
        "lineup_attack_interaction_away": round(away_lineup_attack, 4),
        "absence_penalty_interaction_home": round(absence_home, 4),
        "match_open_score": round(match_open, 4),
        "favorite_pressure_score": round(favorite_pressure, 4),
        "pace_avg": round(pace, 4),
        "home_defensive_weakness_faced": round(home_vs_away_def or 0, 4),
        "away_defensive_weakness_faced": round(away_vs_home_def or 0, 4),
    }
