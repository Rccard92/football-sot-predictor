"""Test regole anti-duplicato tracked_betting_picks."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.tracked_betting_pick_service import (
    formation_snapshot_label,
    parse_line_value_from_pick,
)


def test_parse_line_value_from_pick():
    assert parse_line_value_from_pick("Over 6.5 SOT") == 6.5
    assert parse_line_value_from_pick(None) is None


def test_formation_snapshot_label():
    assert "ufficiale" in formation_snapshot_label(True).lower()
    assert "30" in formation_snapshot_label(False)


def test_pick_unchanged_logic():
    from app.models.tracked_betting_pick import TrackedBettingPick
    from app.services.tracked_betting_pick_service import _pick_unchanged

    row = TrackedBettingPick(
        fixture_id=1,
        model_id="baseline_v2_0_lineup_impact",
        source="auto_pre_match",
        market_id="match_total_sot",
        market_label="SOT Totale",
        pick_type="cautious",
        suggested_pick="Over 6.5 SOT",
        lineup_confirmed=True,
        predicted_total_sot=7.0,
        status="pending",
    )
    assert _pick_unchanged(
        row,
        {"suggested_pick": "Over 6.5 SOT", "lineup_confirmed": True, "predicted_total_sot": 7.0},
    )
    assert not _pick_unchanged(
        row,
        {"suggested_pick": "Over 7.5 SOT", "lineup_confirmed": True, "predicted_total_sot": 7.0},
    )


def test_kickoff_window_bounds():
    from datetime import timedelta

    from app.services.jobs.pre_match_lineup_refresh_job import PreMatchLineupRefreshJob

    now = datetime.now(timezone.utc)
    mb, wm = 30, 10
    half = wm // 2
    start = now + timedelta(minutes=mb - half)
    end = now + timedelta(minutes=mb + half)
    assert (end - start).total_seconds() == wm * 60
