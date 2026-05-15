"""Metadati fonti API/DB per input produzione offensiva v1.1 (nessun calcolo)."""

from __future__ import annotations

INPUT_LABELS: dict[str, str] = {
    "avg_sot_for": "Media tiri in porta fatti",
    "avg_total_shots_for": "Media tiri totali fatti",
    "shot_accuracy_for": "Precisione tiro",
    "avg_inside_box_shots_for": "Media tiri dentro area",
    "avg_outside_box_shots_for": "Media tiri fuori area",
    "avg_blocked_shots_for": "Media tiri bloccati",
    "avg_shots_off_goal_for": "Media tiri fuori dallo specchio",
    "avg_goals_for": "Media goal fatti",
    "offensive_trend": "Trend offensivo recente",
}

INPUT_API_SOURCES: dict[str, str] = {
    "avg_sot_for": "fixtures/statistics::Shots on Goal",
    "avg_total_shots_for": "fixtures/statistics::Total Shots",
    "shot_accuracy_for": "derived",
    "avg_inside_box_shots_for": "fixtures/statistics::Shots insidebox",
    "avg_outside_box_shots_for": "fixtures/statistics::Shots outsidebox",
    "avg_blocked_shots_for": "fixtures/statistics::Blocked Shots",
    "avg_shots_off_goal_for": "fixtures/statistics::Shots off Goal",
    "avg_goals_for": "fixtures::goals",
    "offensive_trend": "fixture_team_stats.shots_on_target",
}

INPUT_SOURCE_PATHS: dict[str, str] = {
    "avg_sot_for": "fixture_team_stats.shots_on_target",
    "avg_total_shots_for": "fixture_team_stats.total_shots",
    "shot_accuracy_for": "derived:shots_on_target/total_shots",
    "avg_inside_box_shots_for": "fixture_team_stats.shots_inside_box",
    "avg_outside_box_shots_for": "fixture_team_stats.shots_outside_box",
    "avg_blocked_shots_for": "fixture_team_stats.blocked_shots",
    "avg_shots_off_goal_for": "fixture_team_stats.shots_off_goal",
    "avg_goals_for": "fixtures.goals",
    "offensive_trend": "derived:last5_sot_minus_season_sot",
}

INPUT_DB_FIELDS: dict[str, str] = {
    "avg_sot_for": "fixture_team_stats.shots_on_target",
    "avg_total_shots_for": "fixture_team_stats.total_shots",
    "shot_accuracy_for": "fixture_team_stats.shots_on_target / fixture_team_stats.total_shots",
    "avg_inside_box_shots_for": "fixture_team_stats.shots_inside_box",
    "avg_outside_box_shots_for": "fixture_team_stats.shots_outside_box",
    "avg_blocked_shots_for": "fixture_team_stats.blocked_shots",
    "avg_shots_off_goal_for": "fixture_team_stats.shots_off_goal",
    "avg_goals_for": "fixtures.goals_home / fixtures.goals_away",
    "offensive_trend": "fixture_team_stats.shots_on_target",
}

OFFENSIVE_INTERNAL_WEIGHTS: dict[str, float] = {
    "avg_sot_for": 0.30,
    "avg_total_shots_for": 0.18,
    "shot_accuracy_for": 0.14,
    "avg_inside_box_shots_for": 0.14,
    "avg_outside_box_shots_for": 0.05,
    "avg_blocked_shots_for": 0.05,
    "avg_shots_off_goal_for": 0.04,
    "avg_goals_for": 0.05,
    "offensive_trend": 0.05,
}

INPUT_ORDER: tuple[str, ...] = tuple(OFFENSIVE_INTERNAL_WEIGHTS.keys())
