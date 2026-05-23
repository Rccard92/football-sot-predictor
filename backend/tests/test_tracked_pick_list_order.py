"""Verifica ordinamento kickoff ASC in list_tracked_payload."""

from __future__ import annotations

import inspect

from app.services.tracked_pick_results_refresh_service import TrackedPickResultsRefreshService


def test_list_tracked_payload_orders_kickoff_asc():
    src = inspect.getsource(TrackedPickResultsRefreshService.list_tracked_payload)
    assert "Fixture.kickoff_at.asc()" in src
    assert "TrackedBettingPick.id.asc()" in src
    assert "kickoff_at.desc()" not in src
