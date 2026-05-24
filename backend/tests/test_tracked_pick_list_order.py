"""Verifica ordinamento kickoff ASC in list_tracked_payload."""

from __future__ import annotations

import inspect

from app.services.tracked_monitoring_dashboard_service import list_tracked_dashboard_payload


def test_list_tracked_payload_orders_kickoff_asc():
    src = inspect.getsource(list_tracked_dashboard_payload)
    assert "Fixture.kickoff_at.asc()" in src
    assert "TrackedBettingPick.id.asc()" in src
    assert "kickoff_at.desc()" not in src
