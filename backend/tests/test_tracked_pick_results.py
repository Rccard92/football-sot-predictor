"""Test esito pick e hint live Over SOT."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.tracked_pick_results_refresh_service import (
    _final_hint_label,
    _live_over_hint,
    _pick_in_scope,
    _resolve_pick_outcome,
    _sot_display_and_reason,
)
from app.models.tracked_betting_pick import STATUS_LIVE, STATUS_LOST, STATUS_PENDING, STATUS_WON


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


def test_final_hint_label():
    assert _final_hint_label(9.0, 8.5) == "Linea superata"
    assert _final_hint_label(8.0, 8.5) == "Linea non superata"


def test_sot_display_live_and_ft():
    live_txt, live_reason = _sot_display_and_reason(
        fixture_status="1H",
        pick_status=STATUS_LIVE,
        result_home_sot=None,
        result_away_sot=None,
        result_total_sot=None,
    )
    assert live_txt == "SOT non disponibili"
    assert live_reason

    ft_txt, _ = _sot_display_and_reason(
        fixture_status="FT",
        pick_status=STATUS_WON,
        result_home_sot=4.0,
        result_away_sot=2.0,
        result_total_sot=6.0,
    )
    assert "4 + 2 = 6" in ft_txt


def test_pick_in_scope_live():
    pick = SimpleNamespace(status=STATUS_PENDING, fixture_status="1H")
    fx = SimpleNamespace(status="1H")
    assert _pick_in_scope(pick, fx, "live") is True
    assert _pick_in_scope(pick, fx, "unfinished") is True
    pick_ft = SimpleNamespace(status=STATUS_WON, fixture_status="FT")
    assert _pick_in_scope(pick_ft, SimpleNamespace(status="FT"), "live") is False
    assert _pick_in_scope(pick_ft, SimpleNamespace(status="FT"), "unfinished") is False
    pick_live_status = SimpleNamespace(status=STATUS_LIVE, fixture_status="NS")
    assert _pick_in_scope(pick_live_status, SimpleNamespace(status="NS"), "live") is True
