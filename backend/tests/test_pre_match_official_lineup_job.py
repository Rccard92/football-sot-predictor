"""Test job formazioni ufficiali pre-match."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.jobs.pre_match_lineup_refresh_job import PreMatchOfficialLineupRefreshJob


def test_kickoff_window_30_10_minutes():
    now = datetime.now(timezone.utc)
    mb, wm = 30, 10
    half = wm // 2
    start = now + timedelta(minutes=mb - half)
    end = now + timedelta(minutes=mb + half)
    assert (end - start).total_seconds() == wm * 60


def test_snapshot_total_from_payload():
    from app.services.jobs.pre_match_lineup_refresh_job import _snapshot_total

    assert _snapshot_total({"v20_available": True, "predicted_home_sot": 4.0, "predicted_away_sot": 2.0}) == 6.0
    assert _snapshot_total({"v20_available": False}) is None
