"""Conteggi advised (GIOCA) vs calculated (tutte le linee WIN/LOSS) per modalità."""

from __future__ import annotations

from typing import Any


def _round1(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 1)


def _hit_rate(wins: int, losses: int) -> float | None:
    total = wins + losses
    if total <= 0:
        return None
    return _round1(100.0 * wins / total)


def _display(plays: int, wins: int, losses: int, hit_rate: float | None) -> str:
    decided = wins + losses
    hr = f"{hit_rate:.1f}%" if hit_rate is not None else "—"
    return f"{wins}/{decided} · {hr}" if decided > 0 else f"0/{plays} · —"


def count_play_mode(block: dict[str, Any], mode: str) -> dict[str, Any]:
    """mode: 'aggressive' | 'cautious'."""
    advice_key = f"{mode}_advice"
    outcome_key = f"{mode}_outcome"
    advice = str(block.get(advice_key) or "").strip().upper()
    outcome = block.get(outcome_key)

    calc_w = calc_l = 0
    adv_w = adv_l = 0
    giocha = non_giocare = borderline = 0

    if advice == "GIOCA":
        giocha += 1
    elif advice == "NON GIOCARE":
        non_giocare += 1
    elif advice == "BORDERLINE":
        borderline += 1

    if outcome in ("WIN", "LOSS"):
        if outcome == "WIN":
            calc_w += 1
        else:
            calc_l += 1
        if advice == "GIOCA":
            if outcome == "WIN":
                adv_w += 1
            else:
                adv_l += 1

    calc_plays = calc_w + calc_l
    adv_plays = adv_w + adv_l
    calc_hr = _hit_rate(calc_w, calc_l)
    adv_hr = _hit_rate(adv_w, adv_l)

    return {
        "plays": adv_plays,
        "wins": adv_w,
        "losses": adv_l,
        "hit_rate": adv_hr,
        "display": _display(adv_plays, adv_w, adv_l, adv_hr),
        "advised": {
            "plays": adv_plays,
            "wins": adv_w,
            "losses": adv_l,
            "hit_rate": adv_hr,
        },
        "calculated": {
            "plays": calc_plays,
            "wins": calc_w,
            "losses": calc_l,
            "hit_rate": calc_hr,
        },
        "advice_counts": {
            "GIOCA": giocha,
            "NON GIOCARE": non_giocare,
            "BORDERLINE": borderline,
        },
    }


def reliability_score(cautious_hit: float | None, aggressive_hit: float | None) -> float | None:
    if cautious_hit is None and aggressive_hit is None:
        return None
    c = float(cautious_hit or 0.0)
    a = float(aggressive_hit or 0.0)
    return round(0.65 * c + 0.35 * a, 1)


def sample_status(advised_plays: int) -> str:
    if advised_plays < 30:
        return "provvisorio"
    if advised_plays < 100:
        return "medio"
    return "solido"


def trend_direction(current: float | None, previous: float | None, threshold: float = 2.0) -> str:
    if current is None or previous is None:
        return "flat"
    delta = current - previous
    if delta >= threshold:
        return "up"
    if delta <= -threshold:
        return "down"
    return "flat"
