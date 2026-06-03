"""Strategia ibrida v31_bias_dynamic_high_guard — base bias_corrected + boost selettivo."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_base_sot import _round1, predict_fixture_totals
from app.services.backtest.v31_calibration_simulator_cohort import CohortStats, get_interactions
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals, _f
from app.services.backtest.v31_calibration_simulator_interactions import (
    compute_fixture_interactions,
    side_strength,
)

HIGH_GUARD_MIN = 4.5
HIGH_GUARD_MAX = 11.5

BOOST_TIER_25 = 52.0
BOOST_TIER_50 = 60.0
BOOST_TIER_75 = 70.0
BOOST_TIER_100 = 80.0

COMPONENT_WEIGHTS: dict[str, float] = {
    "combined_attack_strength": 0.15,
    "combined_sot_strength": 0.10,
    "combined_xg_strength": 0.10,
    "combined_shot_volume_strength": 0.10,
    "opponent_defensive_weakness_combined": 0.15,
    "match_open_score": 0.12,
    "favorite_pressure_score": 0.08,
    "player_layer_attack_strength": 0.10,
    "lineup_attack_ok": 0.10,
    "recent_form_push": 0.10,
}

# Baseline per normalizzazione componente → 0–100 (valori tipici lega)
_COMPONENT_BASELINES: dict[str, tuple[float, float]] = {
    "combined_attack_strength": (6.0, 8.8),
    "combined_sot_strength": (6.0, 9.2),
    "combined_xg_strength": (2.1, 3.2),
    "combined_shot_volume_strength": (20.0, 30.0),
    "opponent_defensive_weakness_combined": (5.8, 9.0),
    "match_open_score": (5.8, 9.0),
    "favorite_pressure_score": (2.8, 4.5),
    "player_layer_attack_strength": (0.90, 1.12),
    "lineup_attack_ok": (0.65, 1.0),
    "recent_form_push": (0.97, 1.12),
}


def _percentile_rank(value: float, cohort_vals: list[float]) -> float:
    if not cohort_vals:
        return 50.0
    if len(cohort_vals) == 1:
        return 100.0 if value >= cohort_vals[0] else 0.0
    below = sum(1 for v in cohort_vals if v < value)
    equal = sum(1 for v in cohort_vals if v == value)
    return max(0.0, min(100.0, 100.0 * (below + 0.5 * equal) / len(cohort_vals)))


def _component_subscore(
    value: float | None,
    key: str,
    *,
    cohort: CohortStats | None = None,
) -> float | None:
    if value is None:
        return None
    if cohort and cohort.signal_component_values.get(key):
        return round(_percentile_rank(float(value), cohort.signal_component_values[key]), 2)
    lo, hi = _COMPONENT_BASELINES[key]
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, 100.0 * (float(value) - lo) / (hi - lo)))


def extract_signal_raw_values(
    signals: FixtureSignals,
    inter: dict[str, Any],
) -> tuple[dict[str, float | None], list[str]]:
    """Estrae valori grezzi per ogni componente del signal 0–100."""
    missing: list[str] = []

    combined_attack = inter.get("combined_offensive_strength")
    combined_sot = inter.get("combined_sot_strength")
    combined_xg = inter.get("combined_xg_strength")

    home_str = side_strength(signals.home.team_raw, signals.home.macros, signals.league_context)
    away_str = side_strength(signals.away.team_raw, signals.away.macros, signals.league_context)
    h_vol = home_str.get("shot_volume_strength")
    a_vol = away_str.get("shot_volume_strength")
    combined_shot = (float(h_vol) + float(a_vol)) if h_vol is not None and a_vol is not None else None

    h_def = inter.get("home_defensive_weakness_faced")
    a_def = inter.get("away_defensive_weakness_faced")
    opp_def = (float(h_def) + float(a_def)) if h_def is not None and a_def is not None else None

    match_open = inter.get("match_open_score")
    fav_pressure = inter.get("favorite_pressure_score")

    h_pl = _f(signals.home.macros.get("player_layer_index"))
    a_pl = _f(signals.away.macros.get("player_layer_index"))
    player_layer = ((h_pl + a_pl) / 2.0) if h_pl is not None and a_pl is not None else None

    home_pl = signals.player_layer.get("home") if isinstance(signals.player_layer, dict) else {}
    away_pl = signals.player_layer.get("away") if isinstance(signals.player_layer, dict) else {}
    xi_h = home_pl.get("starting_xi_available") if isinstance(home_pl, dict) else None
    xi_a = away_pl.get("starting_xi_available") if isinstance(away_pl, dict) else None
    if xi_h is None or xi_a is None:
        lineup_ok: float | None = None
        missing.append("lineup_xi")
    else:
        lineup_ok = 1.0 if (xi_h and xi_a) else 0.65

    h_form = _f(signals.home.macros.get("recent_form_index"))
    a_form = _f(signals.away.macros.get("recent_form_index"))
    recent = ((h_form + a_form) / 2.0) if h_form is not None and a_form is not None else None

    raw_values: dict[str, float | None] = {
        "combined_attack_strength": float(combined_attack) if combined_attack is not None else None,
        "combined_sot_strength": float(combined_sot) if combined_sot is not None else None,
        "combined_xg_strength": float(combined_xg) if combined_xg is not None else None,
        "combined_shot_volume_strength": combined_shot,
        "opponent_defensive_weakness_combined": opp_def,
        "match_open_score": float(match_open) if match_open is not None else None,
        "favorite_pressure_score": float(fav_pressure) if fav_pressure is not None else None,
        "player_layer_attack_strength": player_layer,
        "lineup_attack_ok": lineup_ok,
        "recent_form_push": recent,
    }
    return raw_values, missing


def _percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    s = sorted(vals)
    idx = (len(s) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def compute_high_total_signal(
    signals: FixtureSignals,
    cohort: CohortStats | None = None,
) -> tuple[float, dict[str, Any], list[str]]:
    """Score pre-match 0–100 con redistribuzione pesi se componenti mancanti."""
    inter = get_interactions(signals, cohort)
    raw_values, missing = extract_signal_raw_values(signals, inter)

    subscores: dict[str, float] = {}
    available_weight = 0.0
    for key, weight in COMPONENT_WEIGHTS.items():
        val = raw_values.get(key)
        sub = _component_subscore(val, key, cohort=cohort)
        if sub is None:
            missing.append(key)
            continue
        subscores[key] = round(sub, 2)
        available_weight += weight

    if available_weight <= 0:
        return 50.0, {"fallback": True}, missing

    score = sum(subscores[k] * (COMPONENT_WEIGHTS[k] / available_weight) for k in subscores)
    score = round(max(0.0, min(100.0, score)), 2)

    components = {**subscores, "raw_values": {k: raw_values[k] for k in raw_values}}
    return score, components, missing


def _low_block_active(inter: dict[str, Any]) -> bool:
    pace = float(inter.get("pace_avg") or 1.0)
    comb_xg = float(inter.get("combined_xg_strength") or 0)
    fav = float(inter.get("favorite_pressure_score") or 1.0)
    return pace < 0.98 and comb_xg < 2.4 and fav >= 1.2


def guardrail_multiplier(signals: FixtureSignals, inter: dict[str, Any]) -> tuple[float, list[str]]:
    """Moltiplicatore 0–1; riduce boost senza azzerarlo sistematicamente."""
    mult = 1.0
    reasons: list[str] = []
    dq = signals.data_quality if isinstance(signals.data_quality, dict) else {}
    warnings = int(dq.get("warning_count") or 0)
    status = str(dq.get("team_stats_status") or "ok")

    if status not in ("ok", "partial"):
        return 0.0, ["data_quality_debole"]
    if warnings >= 5:
        return 0.0, ["warning_count_critico"]

    if warnings >= 3:
        mult *= 0.5
        reasons.append("warning_count_alto")

    h_inj = _f(signals.home.macros.get("injuries_unavailable_index")) or 1.0
    a_inj = _f(signals.away.macros.get("injuries_unavailable_index")) or 1.0
    if h_inj < 0.92 or a_inj < 0.92:
        mult *= 0.5
        reasons.append("assenze_offensive_impact")

    h_pace = _f(signals.home.macros.get("pace_control_index")) or 1.0
    a_pace = _f(signals.away.macros.get("pace_control_index")) or 1.0
    if h_pace < 0.92 and a_pace < 0.92:
        mult *= 0.5
        reasons.append("entrambe_low_pace")

    comb_xg = float(inter.get("combined_xg_strength") or 0)
    if comb_xg < 2.2:
        mult *= 0.6
        reasons.append("xg_basso")

    h_pl = _f(signals.home.macros.get("player_layer_index")) or 1.0
    a_pl = _f(signals.away.macros.get("player_layer_index")) or 1.0
    if h_pl < 0.90 or a_pl < 0.90:
        mult *= 0.7
        reasons.append("player_layer_sotto_soglia")

    if _low_block_active(inter):
        mult *= 0.5
        reasons.append("low_block_guard")

    return max(0.0, mult), reasons


def raw_boost_from_signal(signal: float) -> tuple[float, str]:
    if signal >= BOOST_TIER_100:
        return 1.0, "high_guard_tier_100"
    if signal >= BOOST_TIER_75:
        return 0.75, "high_guard_tier_75"
    if signal >= BOOST_TIER_50:
        return 0.50, "high_guard_tier_50"
    if signal >= BOOST_TIER_25:
        return 0.25, "high_guard_tier_25"
    return 0.0, "high_guard_neutral"


def high_guard_boost(
    signal: float,
    signals: FixtureSignals,
    inter: dict[str, Any],
) -> tuple[float, float, float, str, list[str]]:
    """Ritorna raw_boost, multiplier, adjusted_boost, reason, guard_reasons."""
    raw, reason = raw_boost_from_signal(signal)
    mult, guard_reasons = guardrail_multiplier(signals, inter)
    adjusted = round(raw * mult, 4)
    if raw > 0 and adjusted <= 0:
        reason = "guardrail_zeroed"
    elif mult < 1.0 and adjusted > 0:
        reason = f"{reason}_reduced"
    return raw, mult, adjusted, reason, guard_reasons


def apply_high_guard_to_prediction(
    base_pred: dict[str, Any],
    signals: FixtureSignals,
    *,
    cohort: CohortStats | None = None,
) -> dict[str, Any]:
    inter = get_interactions(signals, cohort)
    signal, components, missing = compute_high_total_signal(signals, cohort)
    raw_boost, mult, boost, boost_reason, guards = high_guard_boost(signal, signals, inter)

    total = base_pred.get("predicted_total_sot")
    if total is None:
        return base_pred

    base_total = float(total)
    new_total = max(HIGH_GUARD_MIN, min(HIGH_GUARD_MAX, base_total + boost))
    new_total = _round1(new_total)

    pred = dict(base_pred)
    pred["predicted_total_sot"] = new_total
    trace = dict(pred.get("trace") or {})
    trace["base_predicted_total_sot"] = _round1(base_total)
    trace["high_total_signal"] = signal
    trace["high_total_signal_components"] = components
    trace["high_total_signal_missing"] = missing
    trace["raw_boost"] = raw_boost
    trace["boost_multiplier"] = round(mult, 4)
    trace["boost_applied"] = boost
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


def aggregate_hybrid_debug(
    rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Diagnostica aggregata per strategia hybrid."""
    ok = [r for r in rows if r.get("prediction_status") == "ok"]
    bases: list[float] = []
    finals: list[float] = []
    boosts: list[float] = []
    signals: list[float] = []
    boost_25 = boost_50 = boost_75 = boost_100 = 0
    guard_zero = 0
    top: list[dict[str, Any]] = []

    baseline_by_fid: dict[int, float] = {}
    if baseline_rows:
        for br in baseline_rows:
            if br.get("prediction_status") == "ok" and br.get("predicted_total_sot") is not None:
                baseline_by_fid[int(br.get("fixture_id") or 0)] = float(br["predicted_total_sot"])

    identical_count = 0
    comparable = 0

    for r in ok:
        trace = r.get("trace") if isinstance(r.get("trace"), dict) else {}
        base = trace.get("base_predicted_total_sot")
        if base is None:
            base = r.get("predicted_total_sot")
        final = r.get("predicted_total_sot")
        boost = float(trace.get("boost_applied") or 0)
        sig = float(trace.get("high_total_signal") or 0)

        if base is not None:
            bases.append(float(base))
        if final is not None:
            finals.append(float(final))
        boosts.append(boost)
        signals.append(sig)

        if boost >= 0.99:
            boost_100 += 1
        elif boost >= 0.70:
            boost_75 += 1
        elif boost >= 0.45:
            boost_50 += 1
        elif boost >= 0.20:
            boost_25 += 1

        if trace.get("boost_reason") == "guardrail_zeroed":
            guard_zero += 1

        fid = int(r.get("fixture_id") or 0)
        if fid in baseline_by_fid and final is not None:
            comparable += 1
            if abs(float(final) - baseline_by_fid[fid]) < 0.05:
                identical_count += 1

        if boost > 0:
            top.append(
                {
                    "fixture_id": r.get("fixture_id"),
                    "match": r.get("match"),
                    "base": base,
                    "final": final,
                    "boost": boost,
                    "signal": sig,
                },
            )

    top.sort(key=lambda x: float(x.get("boost") or 0), reverse=True)

    boosted_count = sum(1 for b in boosts if b > 0.01)
    debug: dict[str, Any] = {
        "base_prediction_avg": round(sum(bases) / len(bases), 4) if bases else None,
        "final_prediction_avg": round(sum(finals) / len(finals), 4) if finals else None,
        "boosted_fixtures_count": boosted_count,
        "boost_0_25_count": boost_25,
        "boost_0_50_count": boost_50,
        "boost_0_75_count": boost_75,
        "boost_1_00_count": boost_100,
        "avg_boost_applied": round(sum(boosts) / len(boosts), 4) if boosts else 0.0,
        "max_boost_applied": round(max(boosts), 4) if boosts else 0.0,
        "high_signal_avg": round(sum(signals) / len(signals), 2) if signals else None,
        "high_signal_p75": round(_percentile(signals, 0.75) or 0, 2) if signals else None,
        "high_signal_p90": round(_percentile(signals, 0.90) or 0, 2) if signals else None,
        "guardrail_blocked_count": guard_zero,
        "top_boosted_fixtures": top[:10],
        "identical_to_baseline_pct": round(100.0 * identical_count / comparable, 1) if comparable else None,
    }

    warnings: list[str] = []
    if boosted_count == 0:
        warnings.append("V31_HYBRID_BOOST_NOT_APPLIED")
    if comparable > 0 and identical_count / comparable >= 0.95:
        warnings.append("V31_HYBRID_IDENTICAL_TO_BASELINE")
    debug["hybrid_warnings"] = warnings
    return debug
