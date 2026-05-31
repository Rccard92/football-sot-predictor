"""Logica pura valutazione pick Over SOT — aggressiva + cauta (Step H)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DEFAULT_PICK_LINES: list[float] = [4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5]
DEFAULT_CAUTIOUS_DROP_THRESHOLD = 0.75

PickOutcome = Literal["win", "loss"]
ConfidenceLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ConfidenceSignals:
    min_prior_matches: int
    warnings_count: int
    player_layer_neutral: bool


@dataclass(frozen=True)
class OverPickResult:
    side: str
    line: float
    edge: float
    outcome: PickOutcome | None
    confidence: ConfidenceLevel


def round4(value: float) -> float:
    return round(float(value), 4)


def sorted_lines(lines: list[float]) -> list[float]:
    return sorted(float(line) for line in lines)


def resolve_aggressive_line(predicted_total: float, lines: list[float]) -> float | None:
    below = [line for line in sorted_lines(lines) if line < predicted_total]
    if not below:
        return None
    return below[-1]


def resolve_cautious_line(
    predicted_total: float,
    lines: list[float],
    *,
    cautious_drop_threshold: float = DEFAULT_CAUTIOUS_DROP_THRESHOLD,
) -> tuple[float | None, list[str]]:
    warnings: list[str] = []
    aggressive_line = resolve_aggressive_line(predicted_total, lines)
    if aggressive_line is None:
        return None, warnings

    aggressive_edge = predicted_total - aggressive_line
    if aggressive_edge > cautious_drop_threshold:
        return aggressive_line, warnings

    ordered = sorted_lines(lines)
    idx = ordered.index(aggressive_line)
    if idx == 0:
        warnings.append("no_lower_cautious_line_available")
        return None, warnings
    return ordered[idx - 1], warnings


def compute_pick_outcome(line: float, actual_total: int) -> PickOutcome:
    return "win" if actual_total > line else "loss"


def compute_aggressive_confidence(edge: float) -> ConfidenceLevel:
    if edge <= 0.25:
        return "low"
    if edge <= 0.75:
        return "medium"
    return "high"


def compute_cautious_confidence(edge: float) -> ConfidenceLevel:
    if edge <= 0.75:
        return "medium"
    return "high"


def apply_confidence_caps(base: ConfidenceLevel, signals: ConfidenceSignals) -> ConfidenceLevel:
    if signals.min_prior_matches < 5 or signals.warnings_count >= 8:
        return "low"
    if signals.player_layer_neutral and base == "high":
        return "medium"
    return base


def build_over_pick(
    line: float,
    predicted_total: float,
    actual_total: int | None,
    *,
    confidence_kind: Literal["aggressive", "cautious"],
    signals: ConfidenceSignals,
) -> OverPickResult:
    edge = round4(predicted_total - line)
    if confidence_kind == "aggressive":
        base = compute_aggressive_confidence(edge)
    else:
        base = compute_cautious_confidence(edge)
    confidence = apply_confidence_caps(base, signals)
    outcome = compute_pick_outcome(line, int(actual_total)) if actual_total is not None else None
    return OverPickResult(
        side="over",
        line=float(line),
        edge=edge,
        outcome=outcome,
        confidence=confidence,
    )


def evaluate_over_picks(
    predicted_total: float,
    lines: list[float],
    actual_total: int | None,
    *,
    cautious_drop_threshold: float,
    signals: ConfidenceSignals,
) -> tuple[OverPickResult | None, OverPickResult | None, list[str]]:
    fixture_warnings: list[str] = []
    aggressive_line = resolve_aggressive_line(predicted_total, lines)
    aggressive_pick: OverPickResult | None = None
    if aggressive_line is not None:
        aggressive_pick = build_over_pick(
            aggressive_line,
            predicted_total,
            actual_total,
            confidence_kind="aggressive",
            signals=signals,
        )

    cautious_line, cautious_warnings = resolve_cautious_line(
        predicted_total,
        lines,
        cautious_drop_threshold=cautious_drop_threshold,
    )
    fixture_warnings.extend(cautious_warnings)
    cautious_pick: OverPickResult | None = None
    if cautious_line is not None:
        cautious_pick = build_over_pick(
            cautious_line,
            predicted_total,
            actual_total,
            confidence_kind="cautious",
            signals=signals,
        )

    return aggressive_pick, cautious_pick, fixture_warnings


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
