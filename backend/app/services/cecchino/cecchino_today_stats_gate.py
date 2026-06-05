"""Gate statistiche Cecchino Today."""

from __future__ import annotations

from typing import Any

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
from app.services.cecchino.cecchino_fixture_history import CecchinoFixtureContexts
from app.services.cecchino.cecchino_today_constants import (
    MIN_AWAY_CONTEXT,
    MIN_AWAY_TOTAL,
    MIN_HOME_CONTEXT,
    MIN_HOME_TOTAL,
    MIN_RECENT_CONTEXT_5,
    MIN_RECENT_TOTAL_6,
)


def check_cecchino_today_stats_eligible(
    contexts: CecchinoFixtureContexts,
    *,
    leakage_status: str,
) -> tuple[bool, dict[str, Any], str | None]:
    snapshot = contexts.to_input_snapshot()
    failures: list[str] = []

    thresholds = {
        KEY_HOME_CONTEXT: MIN_HOME_CONTEXT,
        KEY_AWAY_CONTEXT: MIN_AWAY_CONTEXT,
        KEY_HOME_TOTAL: MIN_HOME_TOTAL,
        KEY_AWAY_TOTAL: MIN_AWAY_TOTAL,
        KEY_HOME_RECENT_CONTEXT_5: MIN_RECENT_CONTEXT_5,
        KEY_AWAY_RECENT_CONTEXT_5: MIN_RECENT_CONTEXT_5,
        KEY_HOME_RECENT_TOTAL_6: MIN_RECENT_TOTAL_6,
        KEY_AWAY_RECENT_TOTAL_6: MIN_RECENT_TOTAL_6,
    }

    for key, min_n in thresholds.items():
        block = snapshot.get(key) or {}
        sample = int(block.get("sample_count") or 0)
        if sample < min_n:
            failures.append(f"{key}: sample={sample} < {min_n}")

    if leakage_status == LEAKAGE_FAILED:
        failures.append("leakage_check_failed")

    stats_snapshot = {
        "input_snapshot": snapshot,
        "leakage_status": leakage_status,
        "failures": failures,
    }

    if failures:
        return False, stats_snapshot, ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
    return True, stats_snapshot, None
