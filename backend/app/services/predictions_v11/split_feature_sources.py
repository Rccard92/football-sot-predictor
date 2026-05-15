"""Metadati input Split casa/trasferta v1.1."""

from __future__ import annotations

SPLIT_INPUT_LABELS: dict[str, str] = {
    "split_avg_sot_for": "SOT fatti casa/fuori",
    "split_opponent_avg_sot_conceded": "SOT concessi avversario casa/fuori",
    "split_avg_total_shots_for": "Tiri totali fatti casa/fuori",
    "split_opponent_avg_total_shots_conceded": "Tiri totali concessi avversario casa/fuori",
    "home_away_performance_delta": "Differenza rendimento casa/fuori",
}

SPLIT_INPUT_API_SOURCES: dict[str, str] = {
    "split_avg_sot_for": "fixtures/statistics::Shots on Goal",
    "split_opponent_avg_sot_conceded": "fixtures/statistics::Shots on Goal",
    "split_avg_total_shots_for": "fixtures/statistics::Total Shots",
    "split_opponent_avg_total_shots_conceded": "fixtures/statistics::Total Shots",
    "home_away_performance_delta": "derived",
}

SPLIT_INPUT_SOURCE_PATHS: dict[str, str] = {
    "split_avg_sot_for": "fixture_team_stats.shots_on_target (split casa/fuori squadra)",
    "split_opponent_avg_sot_conceded": "fixture_team_stats.shots_on_target (split avversario)",
    "split_avg_total_shots_for": "fixture_team_stats.total_shots (split casa/fuori squadra)",
    "split_opponent_avg_total_shots_conceded": "fixture_team_stats.total_shots (split avversario)",
    "home_away_performance_delta": "derived:split_avg_sot_for - season_avg_sot_for",
}

SPLIT_INPUT_DB_FIELDS: dict[str, str] = {
    "split_avg_sot_for": "fixture_team_stats.shots_on_target",
    "split_opponent_avg_sot_conceded": "fixture_team_stats.shots_on_target",
    "split_avg_total_shots_for": "fixture_team_stats.total_shots",
    "split_opponent_avg_total_shots_conceded": "fixture_team_stats.total_shots",
    "home_away_performance_delta": "fixture_team_stats.shots_on_target",
}

SPLIT_INTERNAL_WEIGHTS: dict[str, float] = {
    "split_avg_sot_for": 0.30,
    "split_opponent_avg_sot_conceded": 0.30,
    "split_avg_total_shots_for": 0.15,
    "split_opponent_avg_total_shots_conceded": 0.15,
    "home_away_performance_delta": 0.10,
}

SPLIT_INPUT_ORDER: tuple[str, ...] = tuple(SPLIT_INTERNAL_WEIGHTS.keys())

COMPONENT_KEY_SPLIT = "home_away_split_component"
COMPONENT_LABEL_SPLIT = "Split casa/trasferta"
