"""Base SOT assoluta e moltiplicatore contestuale per simulatore v3.1."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_feature_engine import (
    FixtureSignals,
    SideSignals,
    _f,
    _round1,
    _round4,
)
from app.services.backtest.v31_calibration_simulator_trace import normalize_prediction_trace

LEAGUE_AVG_SOT_FOR = 3.35
LEAGUE_AVG_XG_FOR = 1.25
LEAGUE_AVG_SHOTS_FOR = 12.0
# Media tipica totale SOT match (prior lega, non usa target fixture).
LEAGUE_AVG_TOTAL_SOT = 8.0
TOTAL_LEAGUE_BLEND = 0.40

CONTEXT_CAP_MIN = 0.85
CONTEXT_CAP_MAX = 1.15
CORE_CONTEXT_CAP_MIN = 0.92
CORE_CONTEXT_CAP_MAX = 1.08

DEFAULT_BASE_WEIGHTS: dict[str, float] = {
    "avg_sot_for": 0.30,
    "opponent_conceded_sot_avg": 0.25,
    "last5_avg_sot_for": 0.15,
    "home_away_split_sot_for": 0.10,
    "xg_to_sot": 0.10,
    "shots_to_sot": 0.10,
}

EQUAL_BASE_WEIGHTS: dict[str, float] = {
    k: 1.0 / 6 for k in DEFAULT_BASE_WEIGHTS
}

CORE_BASE_WEIGHTS: dict[str, float] = {
    "avg_sot_for": 0.35,
    "opponent_conceded_sot_avg": 0.30,
    "last5_avg_sot_for": 0.10,
    "home_away_split_sot_for": 0.05,
    "xg_to_sot": 0.12,
    "shots_to_sot": 0.08,
}

SPLIT_HEAVY_BASE_WEIGHTS: dict[str, float] = {
    "avg_sot_for": 0.22,
    "opponent_conceded_sot_avg": 0.20,
    "last5_avg_sot_for": 0.10,
    "home_away_split_sot_for": 0.28,
    "xg_to_sot": 0.10,
    "shots_to_sot": 0.10,
}

FORM_HEAVY_BASE_WEIGHTS: dict[str, float] = {
    "avg_sot_for": 0.22,
    "opponent_conceded_sot_avg": 0.18,
    "last5_avg_sot_for": 0.32,
    "home_away_split_sot_for": 0.08,
    "xg_to_sot": 0.10,
    "shots_to_sot": 0.10,
}

CONTEXT_MACRO_WEIGHTS: dict[str, float] = {
    "recent_form_index": 0.20,
    "chance_quality_index": 0.20,
    "pace_control_index": 0.15,
    "home_away_split_index": 0.15,
    "player_layer_index": 0.15,
    "injuries_unavailable_index": 0.10,
    "lineups_index": 0.05,
}

PLAYER_LAYER_CONTEXT_WEIGHTS: dict[str, float] = {
    "recent_form_index": 0.10,
    "chance_quality_index": 0.10,
    "pace_control_index": 0.10,
    "home_away_split_index": 0.10,
    "player_layer_index": 0.30,
    "injuries_unavailable_index": 0.20,
    "lineups_index": 0.10,
}

SPLIT_HEAVY_CONTEXT_WEIGHTS: dict[str, float] = {
    "recent_form_index": 0.12,
    "chance_quality_index": 0.12,
    "pace_control_index": 0.10,
    "home_away_split_index": 0.36,
    "player_layer_index": 0.12,
    "injuries_unavailable_index": 0.10,
    "lineups_index": 0.08,
}

FORM_HEAVY_CONTEXT_WEIGHTS: dict[str, float] = {
    "recent_form_index": 0.38,
    "chance_quality_index": 0.18,
    "pace_control_index": 0.12,
    "home_away_split_index": 0.10,
    "player_layer_index": 0.10,
    "injuries_unavailable_index": 0.07,
    "lineups_index": 0.05,
}

LOW_VARIANCE_BLEND = 0.55
LOW_VARIANCE_TOTAL_MIN = 5.5
LOW_VARIANCE_TOTAL_MAX = 10.5
LOW_VARIANCE_CTX_MIN = 0.93
LOW_VARIANCE_CTX_MAX = 1.07


def league_avgs(league_context: dict[str, Any] | None) -> tuple[float, float, float]:
    lc = league_context if isinstance(league_context, dict) else {}
    sot = _f(lc.get("league_avg_sot_for")) or LEAGUE_AVG_SOT_FOR
    xg = _f(lc.get("league_avg_xg_for")) or LEAGUE_AVG_XG_FOR
    shots = _f(lc.get("league_avg_shots_for")) or LEAGUE_AVG_SHOTS_FOR
    return float(sot), float(xg), float(shots)


def absolute_from_field(
    value: Any,
    league_avg: float,
    field_name: str,
    missing: list[str],
) -> float | None:
    v = _f(value)
    if v is None:
        missing.append(field_name)
        return None
    if 0.65 <= v <= 1.45:
        return league_avg * v
    if 1.5 <= v <= 9.0:
        return v
    missing.append(f"{field_name}_out_of_range")
    return None


def calculate_team_base_sot(
    side_team_raw: dict[str, Any],
    opponent_team_raw: dict[str, Any],
    league_context: dict[str, Any] | None,
    *,
    base_weights: dict[str, float] | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """Base SOT assoluta per una squadra; redistribuisce pesi su campi disponibili."""
    weights = base_weights or DEFAULT_BASE_WEIGHTS
    league_sot, league_xg, league_shots = league_avgs(league_context)
    missing: list[str] = []
    components: dict[str, float | None] = {}

    components["avg_sot_for"] = absolute_from_field(
        side_team_raw.get("avg_sot_for"),
        league_sot,
        "avg_sot_for",
        missing,
    )
    opp_against = opponent_team_raw.get("avg_sot_against") or opponent_team_raw.get(
        "opponent_conceded_sot_avg",
    )
    components["opponent_conceded_sot_avg"] = absolute_from_field(
        opp_against,
        league_sot,
        "opponent_conceded_sot_avg",
        missing,
    )
    components["last5_avg_sot_for"] = absolute_from_field(
        side_team_raw.get("last5_avg_sot_for"),
        league_sot,
        "last5_avg_sot_for",
        missing,
    )
    components["home_away_split_sot_for"] = absolute_from_field(
        side_team_raw.get("home_away_split_sot_for"),
        league_sot,
        "home_away_split_sot_for",
        missing,
    )

    xg_raw = _f(side_team_raw.get("avg_xg_for"))
    if xg_raw is not None:
        if 0.65 <= xg_raw <= 1.45:
            xg_abs = league_xg * xg_raw
        elif 0.3 <= xg_raw <= 3.5:
            xg_abs = xg_raw
        else:
            xg_abs = None
            missing.append("avg_xg_for")
        if xg_abs is not None and league_xg > 0:
            components["xg_to_sot"] = xg_abs * (league_sot / league_xg)
        else:
            components["xg_to_sot"] = None
    else:
        missing.append("avg_xg_for")

    shots_raw = _f(side_team_raw.get("avg_total_shots_for"))
    if shots_raw is not None:
        if 0.65 <= shots_raw <= 1.45:
            shots_abs = league_shots * shots_raw
        elif 4.0 <= shots_raw <= 25.0:
            shots_abs = shots_raw
        else:
            shots_abs = None
        if shots_abs is not None and league_shots > 0:
            components["shots_to_sot"] = shots_abs * (league_sot / league_shots)
        else:
            components["shots_to_sot"] = None
    else:
        missing.append("avg_total_shots_for")

    num = den = 0.0
    used_weights: dict[str, float] = {}
    for key, w in weights.items():
        val = components.get(key)
        if val is None or w <= 0:
            continue
        used_weights[key] = w
        num += w * val
        den += w

    if den <= 0:
        return None, {
            "components": components,
            "missing_fields": missing,
            "base_weights_used": {},
        }

    base = num / den
    base = max(1.8, min(7.0, base))
    sample_size = int(side_team_raw.get("sample_count") or 0)
    return _round4(base), {
        "components": {k: _round4(v) if v is not None else None for k, v in components.items()},
        "missing_fields": missing,
        "base_weights_used": used_weights,
        "league_avgs": {"sot": league_sot, "xg": league_xg, "shots": league_shots},
        "sample_size": sample_size,
    }


def context_multiplier(
    side: SideSignals,
    *,
    cap_min: float = CONTEXT_CAP_MIN,
    cap_max: float = CONTEXT_CAP_MAX,
    context_weights: dict[str, float] | None = None,
) -> tuple[float, dict[str, float]]:
    weights_map = context_weights or CONTEXT_MACRO_WEIGHTS
    used: dict[str, float] = {}
    num = den = 0.0
    for macro_key, w in weights_map.items():
        val = side.macros.get(macro_key)
        if val is None or w <= 0:
            continue
        used[macro_key] = w
        num += w * float(val)
        den += w
    if den <= 0:
        return 1.0, used
    raw = num / den
    capped = max(cap_min, min(cap_max, raw))
    return _round4(capped), used


def predict_fixture_totals(
    signals: FixtureSignals,
    *,
    base_weights: dict[str, float] | None = None,
    context_cap_min: float = CONTEXT_CAP_MIN,
    context_cap_max: float = CONTEXT_CAP_MAX,
    context_weights: dict[str, float] | None = None,
    total_league_blend: float = TOTAL_LEAGUE_BLEND,
    total_min: float = 4.0,
    total_max: float = 14.0,
    side_cap_min: float = 0.8,
    side_cap_max: float = 8.5,
    bias_offset: float = 0.0,
    home_side_multiplier: float = 1.0,
    away_side_multiplier: float = 1.0,
    total_boost: float = 0.0,
    bucket_override_total: float | None = None,
    dynamics_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Predizione home/away/total da base SOT + context multiplier."""
    league_ctx = signals.league_context
    home_base, home_trace = calculate_team_base_sot(
        signals.home.team_raw,
        signals.away.team_raw,
        league_ctx,
        base_weights=base_weights,
    )
    away_base, away_trace = calculate_team_base_sot(
        signals.away.team_raw,
        signals.home.team_raw,
        league_ctx,
        base_weights=base_weights,
    )

    if home_base is None or away_base is None:
        return {
            "predicted_home_sot": None,
            "predicted_away_sot": None,
            "predicted_total_sot": None,
            "trace": {
                "home_base_trace": home_trace,
                "away_base_trace": away_trace,
            },
        }

    h_ctx, h_ctx_w = context_multiplier(
        signals.home,
        cap_min=context_cap_min,
        cap_max=context_cap_max,
        context_weights=context_weights,
    )
    a_ctx, a_ctx_w = context_multiplier(
        signals.away,
        cap_min=context_cap_min,
        cap_max=context_cap_max,
        context_weights=context_weights,
    )

    h_pred = max(side_cap_min, min(side_cap_max, home_base * h_ctx * home_side_multiplier))
    a_pred = max(side_cap_min, min(side_cap_max, away_base * a_ctx * away_side_multiplier))
    raw_total = h_pred + a_pred
    blend = max(0.0, min(1.0, total_league_blend))
    if bucket_override_total is not None:
        total = _round1(float(bucket_override_total))
    else:
        total = _round1((1.0 - blend) * raw_total + blend * LEAGUE_AVG_TOTAL_SOT + bias_offset + total_boost)
    total = max(total_min, min(total_max, total))

    all_missing = list(
        dict.fromkeys(
            signals.missing_fields
            + home_trace.get("missing_fields", [])
            + away_trace.get("missing_fields", []),
        ),
    )

    return {
        "predicted_home_sot": _round1(h_pred),
        "predicted_away_sot": _round1(a_pred),
        "predicted_total_sot": total,
        "home_base_sot": home_base,
        "away_base_sot": away_base,
        "home_context_multiplier": h_ctx,
        "away_context_multiplier": a_ctx,
        "missing_fields": all_missing,
        "trace": normalize_prediction_trace(
            {
                "home_base_trace": home_trace,
                "away_base_trace": away_trace,
                "home_context_weights": h_ctx_w,
                "away_context_weights": a_ctx_w,
                "league_blend_applied": round(blend, 4),
                "total_boost_applied": round(total_boost, 4),
                "boost_applied": round(total_boost, 4),
                "home_side_multiplier": round(home_side_multiplier, 4),
                "away_side_multiplier": round(away_side_multiplier, 4),
                "shots_resolution": getattr(signals, "shots_resolution", {}),
                **(dynamics_trace or {}),
            },
        ),
    }
