"""Classificazione equilibrio partita (tab DASHBOARD)."""

from __future__ import annotations


def classify_match_balance(
    prob_1_decimal: float | None,
    prob_x_decimal: float | None,
    prob_2_decimal: float | None,
) -> str | None:
    if prob_1_decimal is None or prob_x_decimal is None or prob_2_decimal is None:
        return None
    p1, px, p2 = float(prob_1_decimal), float(prob_x_decimal), float(prob_2_decimal)
    if abs(p1 - p2) <= 0.12 and px >= 0.28:
        return "Equilibrio"
    if abs(p1 - p2) >= 0.35:
        return "Squilibrio"
    return "Neutro"
