"""Core regressione e probabilità Over per simulatore v3.1."""

from __future__ import annotations

import math
from typing import Any

from app.services.backtest.v31_calibration_simulator_feature_engine import (
    FixtureSignals,
    V31_MACRO_AREA_KEYS,
    _round1,
    _round4,
)

SIDE_CLAMP = (0.75, 1.35)
LINES = (5.5, 6.5, 7.5, 8.5)


def poisson_cdf(k: int, mu: float) -> float:
    """P(X <= k) per Poisson(mu), k intero >= 0."""
    if mu <= 0:
        return 1.0 if k >= 0 else 0.0
    term = math.exp(-mu)
    acc = term
    for i in range(1, k + 1):
        term *= mu / i
        acc += term
    return min(1.0, max(0.0, acc))


def prob_over_line(mu: float, line: float, sigma_extra: float = 0.0) -> float:
    """P(total > line) con Poisson; sigma_extra allarga implicitamente μ."""
    mu_eff = max(0.5, mu + sigma_extra * 0.15)
    k = int(math.floor(line))
    return _round4(1.0 - poisson_cdf(k, mu_eff))


def macro_blend(
    side: Any,
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """Media pesata macro disponibili; default 1.0 se nessuna macro."""
    used: dict[str, float] = {}
    num = den = 0.0
    for key in V31_MACRO_AREA_KEYS:
        w = weights.get(key, 0.0)
        if w <= 0:
            continue
        val = side.macros.get(key)
        if val is None:
            continue
        used[key] = w
        num += w * float(val)
        den += w
    if den <= 0:
        return 1.0, used
    blend = num / den
    return max(SIDE_CLAMP[0], min(SIDE_CLAMP[1], blend)), used


def predict_sides(
    signals: FixtureSignals,
    *,
    macro_weights: dict[str, float],
    multipliers: dict[str, float] | None = None,
) -> dict[str, Any]:
    mult = multipliers or {}
    home_blend, home_w = macro_blend(signals.home, macro_weights)
    away_blend, away_w = macro_blend(signals.away, macro_weights)

    h_base = signals.home.baseline_sot
    a_base = signals.away.baseline_sot
    if h_base is None or a_base is None:
        return {
            "predicted_home_sot": None,
            "predicted_away_sot": None,
            "predicted_total_sot": None,
            "macro_blend_home": home_blend,
            "macro_blend_away": away_blend,
            "weights_used_home": home_w,
            "weights_used_away": away_w,
        }

    h_pred = h_base * home_blend
    a_pred = a_base * away_blend

    split_m = mult.get("home_away_split", 1.0)
    form_m = mult.get("recent_form", 1.0)
    pl_m = mult.get("player_layer", 1.0)
    inj_m = mult.get("injuries_unavailable", 1.0)
    dq_m = mult.get("data_quality", 1.0)

    h_idx = signals.home.macros.get("home_away_split_index")
    a_idx = signals.away.macros.get("home_away_split_index")
    if h_idx is not None:
        h_pred *= split_m * (0.95 + 0.1 * (float(h_idx) - 1.0))
    if a_idx is not None:
        a_pred *= split_m * (0.95 + 0.1 * (float(a_idx) - 1.0))

    rf_h = signals.home.macros.get("recent_form_index")
    rf_a = signals.away.macros.get("recent_form_index")
    if rf_h is not None:
        h_pred *= form_m * (0.92 + 0.16 * (float(rf_h) - 1.0))
    if rf_a is not None:
        a_pred *= form_m * (0.92 + 0.16 * (float(rf_a) - 1.0))

    pl_h = signals.home.macros.get("player_layer_index")
    pl_a = signals.away.macros.get("player_layer_index")
    if pl_h is not None:
        h_pred *= pl_m * (0.94 + 0.12 * (float(pl_h) - 1.0))
    if pl_a is not None:
        a_pred *= pl_m * (0.94 + 0.12 * (float(pl_a) - 1.0))

    inj_h = signals.home.macros.get("injuries_unavailable_index")
    inj_a = signals.away.macros.get("injuries_unavailable_index")
    if inj_h is not None:
        h_pred *= inj_m * (0.96 + 0.08 * (float(inj_h) - 1.0))
    if inj_a is not None:
        a_pred *= inj_m * (0.96 + 0.08 * (float(inj_a) - 1.0))

    h_pred *= dq_m
    a_pred *= dq_m

    h_pred = max(0.5, min(8.0, h_pred))
    a_pred = max(0.5, min(8.0, a_pred))
    total = _round1(h_pred + a_pred)

    sigma_extra = 0.2 * signals.warning_count + 0.05 * len(signals.missing_fields)
    probs = {f"estimated_probability_over_{str(ln).replace('.', '_')}": prob_over_line(total, ln, sigma_extra) for ln in LINES}

    return {
        "predicted_home_sot": _round1(h_pred),
        "predicted_away_sot": _round1(a_pred),
        "predicted_total_sot": total,
        "macro_blend_home": _round4(home_blend),
        "macro_blend_away": _round4(away_blend),
        "weights_used_home": home_w,
        "weights_used_away": away_w,
        **probs,
        "sigma_extra": sigma_extra,
    }
