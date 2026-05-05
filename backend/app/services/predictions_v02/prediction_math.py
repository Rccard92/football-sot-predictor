from __future__ import annotations

from .math_utils import cap, round2


def compute_confidence_v02(
    *,
    base_score: int,
    has_player_profiles: bool,
    h2h_matches_total: int,
    late_season_risk: bool,
    turnover_high_any: bool,
    availability_not_available: bool,
    abs_total_adjustment: float,
) -> tuple[int, str]:
    s = int(base_score)
    if has_player_profiles:
        s += 3
    if h2h_matches_total >= 5:
        s += 2
    if late_season_risk:
        s -= 8
    if turnover_high_any:
        s -= 8
    if availability_not_available and late_season_risk:
        s -= 10
    if abs_total_adjustment > 0.60:
        s -= 10
    s = int(cap(s, 40, 85))
    if s >= 80:
        return s, "Alta"
    if s >= 60:
        return s, "Media"
    return s, "Bassa"


def compute_adjusted_prediction(
    *,
    baseline_expected_sot: float,
    player_adjustment: float,
    h2h_adjustment: float,
    motivation_adjustment: float,
    availability_adjustment: float,
) -> tuple[float, float]:
    total = cap(
        player_adjustment + h2h_adjustment + motivation_adjustment + availability_adjustment,
        -0.90,
        0.90,
    )
    adjusted = max(1.0, float(baseline_expected_sot) + total)
    return round2(total), round2(adjusted)

