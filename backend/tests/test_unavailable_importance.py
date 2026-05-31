"""Test classify_importance macro indisponibili (Step K.5)."""

from __future__ import annotations

from app.services.backtest.historical_unavailable_macro_service import classify_importance


def test_unmapped_player():
    is_imp, reason = classify_importance(
        mapping_status="no_internal_id",
        role="ST",
        score=0.5,
        prior_matches_count=10,
    )
    assert is_imp is False
    assert reason == "UNMAPPED_PLAYER"


def test_no_prior_stats():
    is_imp, reason = classify_importance(
        mapping_status="no_prior_stats",
        role="LW",
        score=0.2,
        prior_matches_count=0,
    )
    assert is_imp is False
    assert reason == "NO_PRIOR_STATS"


def test_offensive_important():
    is_imp, reason = classify_importance(
        mapping_status="matched",
        role="LW",
        score=0.12,
        prior_matches_count=8,
    )
    assert is_imp is True
    assert reason == "OK"


def test_defensive_only():
    is_imp, reason = classify_importance(
        mapping_status="matched",
        role="CB",
        score=0.02,
        prior_matches_count=12,
    )
    assert is_imp is False
    assert reason == "DEFENSIVE_ONLY"
