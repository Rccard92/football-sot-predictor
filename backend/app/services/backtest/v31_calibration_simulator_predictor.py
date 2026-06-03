"""Probabilità Over (normale) per simulatore v3.1."""

from __future__ import annotations

import math
from typing import Any

from app.services.backtest.v31_calibration_simulator_base_sot import (
    CORE_BASE_WEIGHTS,
    CORE_CONTEXT_CAP_MAX,
    CORE_CONTEXT_CAP_MIN,
    DEFAULT_BASE_WEIGHTS,
    EQUAL_BASE_WEIGHTS,
    predict_fixture_totals,
)
from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals

SIGMA_TOTAL = 2.2
LINES = (5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5)


def _round4(v: float) -> float:
    return round(v, 4)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_over_line(mu: float, line: float, sigma: float = SIGMA_TOTAL) -> float:
    """P(total > line) con Normal(mu, sigma)."""
    if sigma <= 0:
        return 0.0
    z = (line - mu) / sigma
    return _round4(1.0 - norm_cdf(z))


def attach_line_probabilities(pred: dict[str, Any]) -> dict[str, Any]:
    total = pred.get("predicted_total_sot")
    if total is None:
        return pred
    mu = float(total)
    for ln in LINES:
        key = f"estimated_probability_over_{str(ln).replace('.', '_')}"
        pred[key] = prob_over_line(mu, ln)
    pred["sigma_total"] = SIGMA_TOTAL
    return pred


def predict_for_strategy(
    signals: FixtureSignals,
    strategy_key: str,
) -> dict[str, Any]:
    if strategy_key == "v31_equal_weights":
        pred = predict_fixture_totals(signals, base_weights=EQUAL_BASE_WEIGHTS)
    elif strategy_key == "v31_core_sot_xg":
        pred = predict_fixture_totals(
            signals,
            base_weights=CORE_BASE_WEIGHTS,
            context_cap_min=CORE_CONTEXT_CAP_MIN,
            context_cap_max=CORE_CONTEXT_CAP_MAX,
        )
    else:
        pred = predict_fixture_totals(signals, base_weights=DEFAULT_BASE_WEIGHTS)
    return attach_line_probabilities(pred)
