from __future__ import annotations

Signal = str  # "over" | "under" | "no_bet"


def line_signal(expected_sot: float, line_value: float) -> Signal:
    gap = expected_sot - line_value
    if abs(gap) <= 0.25:
        return "no_bet"
    if expected_sot > line_value + 0.25:
        return "over"
    if expected_sot < line_value - 0.25:
        return "under"
    return "no_bet"


def actual_over_line(actual_sot: float, line_value: float) -> bool | None:
    if actual_sot > line_value:
        return True
    if actual_sot < line_value:
        return False
    return None


def line_hit(signal: Signal, actual_over: bool | None) -> bool | None:
    if signal == "no_bet" or actual_over is None:
        return None
    if signal == "over":
        return actual_over is True
    if signal == "under":
        return actual_over is False
    return None
