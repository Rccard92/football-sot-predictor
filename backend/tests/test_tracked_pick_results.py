"""Test esito pick e hint live Over SOT."""

from __future__ import annotations

from app.services.tracked_pick_results_refresh_service import (
    _live_over_hint,
    _resolve_pick_outcome,
)
from app.models.tracked_betting_pick import STATUS_LOST, STATUS_WON


def test_resolve_pick_outcome_over():
    assert _resolve_pick_outcome(9.0, 8.5) == STATUS_WON
    assert _resolve_pick_outcome(8.0, 8.5) == STATUS_LOST
    assert _resolve_pick_outcome(None, 8.5) is None


def test_live_over_hint_beaten():
    h = _live_over_hint(9.0, 8.5)
    assert h["line_already_beaten"] is True
    assert "superata" in (h["live_hint_label"] or "").lower()


def test_live_over_hint_remaining():
    h = _live_over_hint(7.0, 8.5)
    assert h["line_already_beaten"] is False
    assert h["live_sot_remaining"] == 2
    assert "Mancano" in (h["live_hint_label"] or "")
