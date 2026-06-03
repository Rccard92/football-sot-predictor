"""Strategia ibrida v31_bias_dynamic_high_guard — base bias_corrected + boost selettivo."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_base_sot import _round1, predict_fixture_totals
from app.services.backtest.v31_calibration_simulator_cohort import CohortStats
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals, _f
from app.services.backtest.v31_calibration_simulator_interactions import compute_fixture_interactions

HIGH_GUARD_MIN = 4.5
HIGH_GUARD_MAX = 11.5
HIGH_GUARD_MAX_EXTREME = 12.0

SIGNAL_HIGH = 1.0
SIGNAL_VERY_HIGH = 1.4
SIGNAL_EXTREME = 1.8


def _norm_ratio(value: float | None, baseline: float, scale: float = 1.0) -> float:
    if value is None:
        return 0.5
    return max(0.0, min(1.5, (float(value) / baseline) * scale))


def compute_high_total_signal(
    signals: FixtureSignals,
    cohort: CohortStats | None = None,
) -> tuple[float, dict[str, Any]]:
    """Score pre-match 0+ per boost selettivo (no target leakage)."""
    inter = compute_fixture_interactions(signals)
    h_off = float(inter.get("home_offensive_strength") or 3.35)
    a_off = float(inter.get("away_offensive_strength") or 3.35)
    h_def_w = float(inter.get("home_defensive_weakness_faced") or 3.35)
    a_def_w = float(inter.get("away_defensive_weakness_faced") or 3.35)

    combined_attack = _norm_ratio(h_off + a_off, 6.7, 0.5)
    opp_def_weak = _norm_ratio(h_def_w + a_def_w, 6.7, 0.5)
    xg_vol = _norm_ratio(
        (float(inter.get("xg_volume_interaction_home") or 1.0)
         + float(inter.get("xg_volume_interaction_away") or 1.0))
        / 2.0,
        1.0,
    )
    shot_vol = _norm_ratio(
        (float(inter.get("home_offensive_strength") or 3.35)
         + float(inter.get("away_offensive_strength") or 3.35))
        / 6.7,
        1.0,
    )

    h_pl = _f(signals.home.macros.get("player_layer_index")) or 1.0
    a_pl = _f(signals.away.macros.get("player_layer_index")) or 1.0
    player_attack = _norm_ratio((h_pl + a_pl) / 2.0, 1.0)

    home_pl = signals.player_layer.get("home") if isinstance(signals.player_layer, dict) else {}
    away_pl = signals.player_layer.get("away") if isinstance(signals.player_layer, dict) else {}
    xi_ok = 1.0 if (home_pl.get("starting_xi_available") and away_pl.get("starting_xi_available")) else 0.6
    lineup_ok = _norm_ratio(xi_ok, 1.0)

    h_form = _f(signals.home.macros.get("recent_form_index")) or 1.0
    a_form = _f(signals.away.macros.get("recent_form_index")) or 1.0
    recent_push = _norm_ratio((h_form + a_form) / 2.0, 1.0)

    components = {
        "combined_attack_strength": round(combined_attack, 4),
        "opponent_defensive_weakness_combined": round(opp_def_weak, 4),
        "xg_volume_interaction": round(xg_vol, 4),
        "shot_volume_interaction": round(shot_vol, 4),
        "player_layer_attack_strength": round(player_attack, 4),
        "lineup_attack_ok": round(lineup_ok, 4),
        "recent_form_push": round(recent_push, 4),
    }

    signal = (
        0.25 * combined_attack
        + 0.20 * opp_def_weak
        + 0.15 * xg_vol
        + 0.15 * shot_vol
        + 0.10 * player_attack
        + 0.10 * lineup_ok
        + 0.05 * recent_push
    )

    if cohort and getattr(cohort, "high_signal_p70", None):
        signal *= 1.0 + min(0.15, max(0, signal - cohort.high_signal_p70) * 0.2)

    return round(signal, 4), components


def _low_block_active(inter: dict[str, Any]) -> bool:
    pace = float(inter.get("pace_avg") or 1.0)
    comb_xg = float(inter.get("combined_xg_strength") or 0)
    fav = float(inter.get("favorite_pressure_score") or 1.0)
    return pace < 0.98 and comb_xg < 2.4 and fav >= 1.2


def guardrails_block_boost(signals: FixtureSignals, inter: dict[str, Any]) -> tuple[bool, list[str]]:
    """True se boost va soppresso."""
    reasons: list[str] = []
    dq = signals.data_quality if isinstance(signals.data_quality, dict) else {}
    warnings = int(dq.get("warning_count") or 0)
    if warnings >= 3:
        reasons.append("warning_count_alto")
    status = str(dq.get("team_stats_status") or "ok")
    if status not in ("ok", "partial"):
        reasons.append("data_quality_debole")

    h_inj = _f(signals.home.macros.get("injuries_unavailable_index")) or 1.0
    a_inj = _f(signals.away.macros.get("injuries_unavailable_index")) or 1.0
    if h_inj < 0.92 or a_inj < 0.92:
        reasons.append("assenze_offensive_impact")

    h_pace = _f(signals.home.macros.get("pace_control_index")) or 1.0
    a_pace = _f(signals.away.macros.get("pace_control_index")) or 1.0
    if h_pace < 0.92 and a_pace < 0.92:
        reasons.append("entrambe_low_pace")

    comb_xg = float(inter.get("combined_xg_strength") or 0)
    if comb_xg < 2.2:
        reasons.append("xg_basso")

    h_pl = _f(signals.home.macros.get("player_layer_index")) or 1.0
    a_pl = _f(signals.away.macros.get("player_layer_index")) or 1.0
    if h_pl < 0.90 or a_pl < 0.90:
        reasons.append("player_layer_sotto_soglia")

    if _low_block_active(inter):
        reasons.append("low_block_guard")

    return len(reasons) > 0, reasons


def high_guard_boost(
    signal: float,
    signals: FixtureSignals,
    inter: dict[str, Any],
) -> tuple[float, str, list[str]]:
    blocked, guard_reasons = guardrails_block_boost(signals, inter)
    if blocked:
        return 0.0, "guardrail_blocked", guard_reasons

    if signal >= SIGNAL_EXTREME:
        return 1.0, "high_guard_extreme", guard_reasons
    if signal >= SIGNAL_VERY_HIGH:
        return 0.70, "high_guard_very_high", guard_reasons
    if signal >= SIGNAL_HIGH:
        return 0.35, "high_guard_high", guard_reasons
    return 0.0, "high_guard_neutral", guard_reasons


def apply_high_guard_to_prediction(
    base_pred: dict[str, Any],
    signals: FixtureSignals,
    *,
    cohort: CohortStats | None = None,
) -> dict[str, Any]:
    """Applica boost su predizione base bias_corrected."""
    inter = compute_fixture_interactions(signals)
    signal, components = compute_high_total_signal(signals, cohort)
    boost, boost_reason, guards = high_guard_boost(signal, signals, inter)

    total = base_pred.get("predicted_total_sot")
    if total is None:
        return base_pred

    new_total = float(total) + boost
    max_cap = HIGH_GUARD_MAX_EXTREME if boost >= 1.0 and boost_reason == "high_guard_extreme" else HIGH_GUARD_MAX
    new_total = max(HIGH_GUARD_MIN, min(max_cap, new_total))
    new_total = _round1(new_total)

    pred = dict(base_pred)
    pred["predicted_total_sot"] = new_total
    trace = dict(pred.get("trace") or {})
    trace["high_total_signal"] = signal
    trace["high_total_signal_components"] = components
    trace["boost_applied"] = round(boost, 4)
    trace["boost_reason"] = boost_reason
    trace["guardrails_blocked"] = guards
    trace["base_strategy"] = "v31_bias_corrected"
    trace["interaction_scores"] = inter
    pred["trace"] = trace
    return pred


def _predict_bias_corrected_base(
    signals: FixtureSignals,
    *,
    bias_offset: float = 0.0,
) -> dict[str, Any]:
    """Base numerica identica a v31_bias_corrected (senza import circolare)."""
    from app.services.backtest.v31_calibration_simulator_predictor import STRATEGY_REGISTRY

    spec = STRATEGY_REGISTRY["v31_bias_corrected"]
    return predict_fixture_totals(
        signals,
        base_weights=spec.base_weights,
        context_cap_min=spec.context_cap_min,
        context_cap_max=spec.context_cap_max,
        context_weights=spec.context_weights,
        total_league_blend=spec.total_league_blend,
        total_min=spec.total_min,
        total_max=spec.total_max,
        side_cap_min=spec.side_cap_min,
        side_cap_max=spec.side_cap_max,
        bias_offset=bias_offset,
    )


def predict_high_guard(
    signals: FixtureSignals,
    *,
    bias_offset: float = 0.0,
    cohort: CohortStats | None = None,
) -> dict[str, Any]:
    base = _predict_bias_corrected_base(signals, bias_offset=bias_offset)
    out = apply_high_guard_to_prediction(base, signals, cohort=cohort)
    trace = out.get("trace") or {}
    trace["strategy_key"] = "v31_bias_dynamic_high_guard"
    trace["bias_offset_applied"] = round(bias_offset, 4)
    out["trace"] = trace
    return out
