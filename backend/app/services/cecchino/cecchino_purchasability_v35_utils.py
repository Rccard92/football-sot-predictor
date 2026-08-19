"""Utility matematiche V3.5 — autonome da Purchasability V1 Preview."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.services.cecchino.cecchino_purchasability_v35_config import CLASS_THRESHOLDS


def clamp_v35(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def round_score_v35(raw_score: float) -> int:
    """Arrotondamento ufficiale V3.5: Decimal ROUND_HALF_UP 0–100."""
    clamped = clamp_v35(float(raw_score), 0.0, 100.0)
    return int(
        Decimal(str(clamped)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def classify_score_v35(score: int | float | None) -> str | None:
    if score is None:
        return None
    s = float(score)
    if s < CLASS_THRESHOLDS[0]:
        return "Molto Bassa"
    if s < CLASS_THRESHOLDS[1]:
        return "Bassa"
    if s < CLASS_THRESHOLDS[2]:
        return "Media"
    if s < CLASS_THRESHOLDS[3]:
        return "Alta"
    return "Molto Alta"
