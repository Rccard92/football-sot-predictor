"""Test alias SOT in statistics_list_to_fields."""

from __future__ import annotations

from app.services.fixture_team_stats_mapping import statistics_list_to_fields


def test_shots_on_target_aliases():
    for label in ("Shots on Goal", "Shots on Target", "Tiri in porta", "On Target"):
        parsed = statistics_list_to_fields([{"type": label, "value": 5}])
        assert parsed.get("shots_on_target") == 5
