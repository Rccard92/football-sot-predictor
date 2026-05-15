"""Metadati input Forma recente v1.1 (ultime 5 partite)."""

from __future__ import annotations

RECENT_INPUT_LABELS: dict[str, str] = {
    "recent_avg_sot_for": "SOT fatti ultime 5",
    "recent_opponent_avg_sot_conceded": "SOT concessi avversario ultime 5",
    "recent_avg_total_shots_for": "Tiri totali fatti ultime 5",
    "recent_opponent_avg_total_shots_conceded": "Tiri totali concessi avversario ultime 5",
    "recent_avg_goals_for": "Goal fatti ultime 5",
    "recent_trend_vs_season": "Trend rispetto alla media stagionale",
}

RECENT_INPUT_API_SOURCES: dict[str, str] = {
    "recent_avg_sot_for": "fixtures/statistics::Shots on Goal",
    "recent_opponent_avg_sot_conceded": "fixtures/statistics::Shots on Goal",
    "recent_avg_total_shots_for": "fixtures/statistics::Total Shots",
    "recent_opponent_avg_total_shots_conceded": "fixtures/statistics::Total Shots",
    "recent_avg_goals_for": "fixtures::goals",
    "recent_trend_vs_season": "derived",
}

RECENT_INPUT_SOURCE_PATHS: dict[str, str] = {
    "recent_avg_sot_for": "fixture_team_stats.shots_on_target (ultime 5 partite squadra)",
    "recent_opponent_avg_sot_conceded": "fixture_team_stats.shots_on_target (ultime 5 partite avversario, concessi)",
    "recent_avg_total_shots_for": "fixture_team_stats.total_shots (ultime 5 partite squadra)",
    "recent_opponent_avg_total_shots_conceded": "fixture_team_stats.total_shots (ultime 5 avversario, concessi)",
    "recent_avg_goals_for": "fixtures.goals_home / fixtures.goals_away (ultime 5)",
    "recent_trend_vs_season": "derived:blend(delta_squadra,delta_avversario) vs stagione",
}

RECENT_INPUT_DB_FIELDS: dict[str, str] = {
    "recent_avg_sot_for": "fixture_team_stats.shots_on_target",
    "recent_opponent_avg_sot_conceded": "fixture_team_stats.shots_on_target",
    "recent_avg_total_shots_for": "fixture_team_stats.total_shots",
    "recent_opponent_avg_total_shots_conceded": "fixture_team_stats.total_shots",
    "recent_avg_goals_for": "fixtures.goals",
    "recent_trend_vs_season": "fixture_team_stats.shots_on_target",
}

RECENT_INTERNAL_WEIGHTS: dict[str, float] = {
    "recent_avg_sot_for": 0.25,
    "recent_opponent_avg_sot_conceded": 0.25,
    "recent_avg_total_shots_for": 0.15,
    "recent_opponent_avg_total_shots_conceded": 0.15,
    "recent_avg_goals_for": 0.10,
    "recent_trend_vs_season": 0.10,
}

RECENT_INPUT_ORDER: tuple[str, ...] = tuple(RECENT_INTERNAL_WEIGHTS.keys())

COMPONENT_KEY_RECENT = "recent_form_component"
COMPONENT_LABEL_RECENT = "Forma recente"
