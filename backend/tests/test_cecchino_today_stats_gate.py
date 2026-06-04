"""Test gate statistiche Cecchino Today."""

from __future__ import annotations

from app.models.cecchino_today_fixture import ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
from app.services.cecchino.cecchino_constants import (
    KEY_AWAY_CONTEXT,
    KEY_AWAY_RECENT_CONTEXT_5,
    KEY_AWAY_RECENT_TOTAL_6,
    KEY_AWAY_TOTAL,
    KEY_HOME_CONTEXT,
    KEY_HOME_RECENT_CONTEXT_5,
    KEY_HOME_RECENT_TOTAL_6,
    KEY_HOME_TOTAL,
    LEAKAGE_FAILED,
    LEAKAGE_PASSED,
)
from app.services.cecchino.cecchino_engine import WDLRecord
from app.services.cecchino.cecchino_fixture_history import CecchinoFixtureContexts, WDLContextSlice
from app.services.cecchino.cecchino_today_stats_gate import check_cecchino_today_stats_eligible


def _slice(key: str, n: int, target: int | None = None) -> WDLContextSlice:
    return WDLContextSlice(
        key=key,
        wdl=WDLRecord(wins=1, draws=1, losses=1),
        sample_count=n,
        target_sample=target,
    )


def _contexts(**counts: int) -> CecchinoFixtureContexts:
    defaults = {
        KEY_HOME_CONTEXT: 3,
        KEY_AWAY_CONTEXT: 3,
        KEY_HOME_TOTAL: 6,
        KEY_AWAY_TOTAL: 6,
        KEY_HOME_RECENT_CONTEXT_5: 3,
        KEY_AWAY_RECENT_CONTEXT_5: 3,
        KEY_HOME_RECENT_TOTAL_6: 5,
        KEY_AWAY_RECENT_TOTAL_6: 5,
    }
    defaults.update(counts)
    return CecchinoFixtureContexts(
        home_context=_slice(KEY_HOME_CONTEXT, defaults[KEY_HOME_CONTEXT]),
        away_context=_slice(KEY_AWAY_CONTEXT, defaults[KEY_AWAY_CONTEXT]),
        home_total=_slice(KEY_HOME_TOTAL, defaults[KEY_HOME_TOTAL]),
        away_total=_slice(KEY_AWAY_TOTAL, defaults[KEY_AWAY_TOTAL]),
        home_recent_context_5=_slice(KEY_HOME_RECENT_CONTEXT_5, defaults[KEY_HOME_RECENT_CONTEXT_5], 3),
        away_recent_context_5=_slice(KEY_AWAY_RECENT_CONTEXT_5, defaults[KEY_AWAY_RECENT_CONTEXT_5], 3),
        home_recent_total_6=_slice(KEY_HOME_RECENT_TOTAL_6, defaults[KEY_HOME_RECENT_TOTAL_6], 5),
        away_recent_total_6=_slice(KEY_AWAY_RECENT_TOTAL_6, defaults[KEY_AWAY_RECENT_TOTAL_6], 5),
    )


def test_stats_sufficient_with_leakage_passed():
    ok, snap, reason = check_cecchino_today_stats_eligible(_contexts(), leakage_status=LEAKAGE_PASSED)
    assert ok
    assert reason is None
    assert snap["failures"] == []


def test_stats_insufficient_home_context():
    ok, snap, reason = check_cecchino_today_stats_eligible(
        _contexts(**{KEY_HOME_CONTEXT: 2}),
        leakage_status=LEAKAGE_PASSED,
    )
    assert not ok
    assert reason == ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
    assert any("home_context" in f for f in snap["failures"])


def test_stats_leakage_failed():
    ok, snap, reason = check_cecchino_today_stats_eligible(_contexts(), leakage_status=LEAKAGE_FAILED)
    assert not ok
    assert reason == ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
    assert "leakage_check_failed" in snap["failures"]
