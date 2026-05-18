"""Helper condivisi availability (no import predictions_v11)."""

from __future__ import annotations

from decimal import Decimal

from app.models import PlayerSeasonProfile
from app.services.sot_feature_registry import V11_MIN_PLAYER_MINUTES

TOP_SHOOTERS_TOTAL = 5
HIGH_IMPACT_THRESHOLD = 70.0


def _float_from_decimal(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    return float(v)


def _eligible_profile(p: PlayerSeasonProfile) -> bool:
    mins = p.minutes_total
    if mins is None or float(mins) < V11_MIN_PLAYER_MINUTES:
        return False
    if p.reliability_score is None:
        return False
    if p.shots_on_per90 is None and p.shots_total_per90 is None:
        return False
    return True


def _sort_key_profile(p: PlayerSeasonProfile) -> tuple:
    impact = _float_from_decimal(p.shooting_impact_score)
    sot90 = _float_from_decimal(p.shots_on_per90)
    mins = _float_from_decimal(p.minutes_total)
    return (
        impact is None,
        -(impact or 0.0),
        -(sot90 or 0.0),
        -(mins or 0.0),
    )


def select_top_shooter_api_ids(
    profiles: dict[int, PlayerSeasonProfile],
    *,
    limit: int = TOP_SHOOTERS_TOTAL,
) -> list[int]:
    eligible = [p for p in profiles.values() if _eligible_profile(p)]
    eligible.sort(key=_sort_key_profile)
    return [int(p.api_player_id) for p in eligible[:limit]]
