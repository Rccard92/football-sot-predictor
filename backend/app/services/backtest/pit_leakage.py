"""Helper anti-leakage strict cutoff per PointInTimeContext (PIT backtest)."""

from __future__ import annotations

from datetime import datetime

from app.services.sot_feature_math import fixture_key_before


def pit_strict_kickoff_before(kickoff_a: datetime, cutoff_kickoff: datetime) -> bool:
    """True solo se kickoff_a è strettamente prima del cutoff (no contemporanee)."""
    return kickoff_a < cutoff_kickoff


def is_prior_fixture(
    kickoff_a: datetime,
    fixture_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    *,
    strict_kickoff_only: bool = False,
) -> bool:
    if strict_kickoff_only:
        return pit_strict_kickoff_before(kickoff_a, cutoff_kickoff)
    return fixture_key_before(kickoff_a, fixture_id, cutoff_kickoff, cutoff_fixture_id)


def compute_leakage_guard(cutoff: datetime, *latest_timestamps: datetime | None) -> bool:
    latest_values = [t for t in latest_timestamps if t is not None]
    if not latest_values:
        return True
    return max(latest_values) < cutoff
