"""Bloccati e Shots off Goal: parsing, backfill su raw_json, aggregazione lettura."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.fixture_team_stats_mapping import (
    STAT_LABEL_ALIASES,
    backfill_shot_columns_from_raw_json_if_null,
    statistics_list_to_fields,
)
from app.services.predictions_v11.shared_stats import agg_for_team, blocked_shots_from_team_stat, shots_off_goal_from_team_stat


def test_alias_shots_off_target_maps_to_goal_key():
    assert STAT_LABEL_ALIASES["shots off target"] == "shots_off_goal"


def test_statistics_list_accepts_zero_for_int_metrics():
    out = statistics_list_to_fields([{"type": "Shots off Goal", "value": 0}, {"type": "Blocked Shots", "value": 0}])
    assert out.get("shots_off_goal") == 0
    assert out.get("blocked_shots") == 0


def test_backfill_fills_only_null_columns_from_raw_json():
    row = SimpleNamespace(
        blocked_shots=None,
        shots_off_goal=None,
        raw_json={
            "statistics": [
                {"type": "Blocked Shots", "value": 3},
                {"type": "Shots off Goal", "value": "2"},
            ],
        },
    )
    backfill_shot_columns_from_raw_json_if_null(row)
    assert row.blocked_shots == 3
    assert row.shots_off_goal == 2


def test_backfill_does_not_overwrite_existing_columns():
    row = SimpleNamespace(
        blocked_shots=9,
        shots_off_goal=None,
        raw_json={"statistics": [{"type": "Blocked Shots", "value": 1}, {"type": "Shots off Goal", "value": 7}]},
    )
    backfill_shot_columns_from_raw_json_if_null(row)
    assert row.blocked_shots == 9
    assert row.shots_off_goal == 7


def test_helpers_read_column_before_raw_json():
    st_col = SimpleNamespace(
        blocked_shots=5,
        shots_off_goal=None,
        raw_json={"statistics": [{"type": "Shots off Goal", "value": 99}]},
    )
    b, bp = blocked_shots_from_team_stat(st_col)
    assert b == 5
    assert bp == "fixture_team_stats.blocked_shots"
    og, op = shots_off_goal_from_team_stat(st_col)
    assert og == 99
    assert "raw_json" in op


def test_agg_for_team_counts_raw_when_columns_null():
    fx = SimpleNamespace(
        id=1,
        kickoff_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        home_team_id=10,
        away_team_id=20,
        goals_home=1,
        goals_away=0,
    )
    st = SimpleNamespace(
        shots_on_target=3,
        total_shots=10,
        shots_inside_box=4,
        shots_outside_box=3,
        blocked_shots=None,
        shots_off_goal=None,
        raw_json={
            "statistics": [
                {"type": "Blocked Shots", "value": "4"},
                {"type": "Shots off Goal", "value": 2},
            ],
        },
    )
    agg = agg_for_team(fixtures=[fx], stats_map={(1, 10): st}, team_id=10)
    assert agg["blocked_n"] == 1
    assert agg["off_goal_n"] == 1
    assert float(agg["blocked_mean"]) == 4.0
    assert float(agg["off_goal_mean"]) == 2.0
    assert "|" in str(agg["blocked_shots_trace_path"])
    assert "|" in str(agg["shots_off_goal_trace_path"])
