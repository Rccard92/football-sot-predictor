"""Logica pura valutazione pick Over/Under SOT (Step H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DEFAULT_PICK_LINES: list[float] = [5.5, 6.5, 7.5, 8.5, 9.5]

PickSide = Literal["over", "under"]
PickOutcome = Literal["win", "loss"]
ConfidenceLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class PickCandidate:
    side: PickSide
    line: float
    edge: float


@dataclass(frozen=True)
class LineEvaluationResult:
    line: float
    edge_over: float
    edge_under: float
    over_meets_min_edge: bool
    under_meets_min_edge: bool


@dataclass(frozen=True)
class ConfidenceSignals:
    mode: str
    min_prior_matches: int
    warnings_count: int
    player_layer_neutral: bool


def round4(value: float) -> float:
    return round(float(value), 4)


def evaluate_line(predicted_total: float, line: float, min_edge: float) -> LineEvaluationResult:
    edge_over = round4(predicted_total - line)
    edge_under = round4(line - predicted_total)
    return LineEvaluationResult(
        line=float(line),
        edge_over=edge_over,
        edge_under=edge_under,
        over_meets_min_edge=edge_over >= min_edge,
        under_meets_min_edge=edge_under >= min_edge,
    )


def collect_candidates(
    predicted_total: float,
    lines: list[float],
    min_edge: float,
) -> tuple[list[LineEvaluationResult], list[PickCandidate]]:
    evaluations: list[LineEvaluationResult] = []
    candidates: list[PickCandidate] = []
    for line in lines:
        ev = evaluate_line(predicted_total, float(line), min_edge)
        evaluations.append(ev)
        if ev.over_meets_min_edge:
            candidates.append(PickCandidate(side="over", line=float(line), edge=ev.edge_over))
        if ev.under_meets_min_edge:
            candidates.append(PickCandidate(side="under", line=float(line), edge=ev.edge_under))
    return evaluations, candidates


def select_recommended_pick(candidates: list[PickCandidate]) -> PickCandidate | None:
    if not candidates:
        return None
    return max(candidates, key=lambda c: abs(c.edge))


def compute_pick_outcome(side: PickSide, line: float, actual_total: int) -> PickOutcome:
    if side == "over":
        return "win" if actual_total > line else "loss"
    return "win" if actual_total < line else "loss"


def compute_base_confidence(edge_abs: float) -> ConfidenceLevel:
    if edge_abs >= 2.0:
        return "high"
    if edge_abs >= 1.25:
        return "medium"
    return "low"


def apply_confidence_caps(base: ConfidenceLevel, signals: ConfidenceSignals) -> ConfidenceLevel:
    level = base
    if signals.min_prior_matches < 5 or signals.warnings_count >= 8:
        return "low"
    if signals.player_layer_neutral and level == "high":
        return "medium"
    if signals.mode == "pre_lineup" and signals.player_layer_neutral and level == "high":
        return "medium"
    return level


def sample_bucket_key(home_prior: int, away_prior: int) -> str:
    min_prior = min(home_prior, away_prior)
    if min_prior < 5:
        return "early_low_sample"
    if min_prior <= 14:
        return "medium_sample"
    return "stable_sample"


def actual_total_bucket_key(actual_total: int | None) -> str | None:
    if actual_total is None:
        return None
    if actual_total <= 6:
        return "low_total"
    if actual_total <= 10:
        return "medium_total"
    return "high_total"


def player_layer_is_neutral(home_status: str | None, away_status: str | None) -> bool:
    statuses = [s for s in (home_status, away_status) if s]
    if not statuses:
        return True
    return all(s in ("neutral_fallback", "not_built_yet") for s in statuses)
