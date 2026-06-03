"""Percentili cohort pre-match per strategie dinamiche v3.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.backtest.v31_calibration_simulator_feature_engine import (
    FixtureSignals,
    extract_fixture_signals,
)
from app.services.backtest.v31_calibration_simulator_interactions import (
    compute_fixture_interactions,
)


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


@dataclass
class CohortStats:
    offensive_p65: float = 6.5
    offensive_p75: float = 7.0
    combined_offensive_p65: float = 13.0
    combined_offensive_p75: float = 14.0
    match_open_p70: float = 2.2
    favorite_pressure_p70: float = 1.3
    fixture_interactions: dict[int, dict[str, Any]] = field(default_factory=dict)


def build_cohort_from_rows(rows: list[dict[str, Any]]) -> CohortStats:
    off_vals: list[float] = []
    comb_vals: list[float] = []
    open_vals: list[float] = []
    fav_vals: list[float] = []
    interactions: dict[int, dict[str, Any]] = {}

    for row in rows:
        signals = extract_fixture_signals(row)
        if signals is None:
            continue
        inter = compute_fixture_interactions(signals)
        interactions[signals.fixture_id] = inter
        off_vals.append(float(inter["home_offensive_strength"]))
        off_vals.append(float(inter["away_offensive_strength"]))
        comb_vals.append(float(inter["combined_offensive_strength"]))
        open_vals.append(float(inter["match_open_score"]))
        fav_vals.append(float(inter["favorite_pressure_score"]))

    off_sorted = sorted(off_vals)
    comb_sorted = sorted(comb_vals)
    open_sorted = sorted(open_vals)
    fav_sorted = sorted(fav_vals)

    return CohortStats(
        offensive_p65=_percentile(off_sorted, 0.65),
        offensive_p75=_percentile(off_sorted, 0.75),
        combined_offensive_p65=_percentile(comb_sorted, 0.65),
        combined_offensive_p75=_percentile(comb_sorted, 0.75),
        match_open_p70=_percentile(open_sorted, 0.70),
        favorite_pressure_p70=_percentile(fav_sorted, 0.70),
        fixture_interactions=interactions,
    )


def get_interactions(
    signals: FixtureSignals,
    cohort: CohortStats | None,
) -> dict[str, Any]:
    if cohort and signals.fixture_id in cohort.fixture_interactions:
        return cohort.fixture_interactions[signals.fixture_id]
    return compute_fixture_interactions(signals)
