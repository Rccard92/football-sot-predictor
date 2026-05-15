"""Metadati input Resistenza difensiva avversaria v1.1."""

from __future__ import annotations

DEFENSIVE_INPUT_LABELS: dict[str, str] = {
    "opponent_avg_sot_conceded": "SOT concessi avversario stagione",
    "opponent_avg_total_shots_conceded": "Tiri totali concessi avversario",
    "opponent_avg_inside_box_shots_conceded": "Tiri dentro area concessi avversario",
    "opponent_avg_outside_box_shots_conceded": "Tiri fuori area concessi avversario",
    "opponent_avg_blocked_shots_conceded": "Tiri bloccati concessi avversario",
    "opponent_defensive_trend_recent": "Trend difensivo recente avversario",
}

DEFENSIVE_INPUT_API_SOURCES: dict[str, str] = {
    "opponent_avg_sot_conceded": "fixtures/statistics::Shots on Goal",
    "opponent_avg_total_shots_conceded": "fixtures/statistics::Total Shots",
    "opponent_avg_inside_box_shots_conceded": "fixtures/statistics::Shots insidebox",
    "opponent_avg_outside_box_shots_conceded": "fixtures/statistics::Shots outsidebox",
    "opponent_avg_blocked_shots_conceded": "fixtures/statistics::Blocked Shots",
    "opponent_defensive_trend_recent": "derived",
}

DEFENSIVE_INPUT_SOURCE_PATHS: dict[str, str] = {
    "opponent_avg_sot_conceded": "fixture_team_stats.shots_on_target (avversari dell'avversario)",
    "opponent_avg_total_shots_conceded": "fixture_team_stats.total_shots (avversari dell'avversario)",
    "opponent_avg_inside_box_shots_conceded": "fixture_team_stats.shots_inside_box (avversari dell'avversario)",
    "opponent_avg_outside_box_shots_conceded": "fixture_team_stats.shots_outside_box (avversari dell'avversario)",
    "opponent_avg_blocked_shots_conceded": "fixture_team_stats.blocked_shots (avversari dell'avversario)",
    "opponent_defensive_trend_recent": "derived:last5_sot_conceded_minus_season_sot_conceded",
}

DEFENSIVE_INPUT_DB_FIELDS: dict[str, str] = {
    "opponent_avg_sot_conceded": "fixture_team_stats.shots_on_target",
    "opponent_avg_total_shots_conceded": "fixture_team_stats.total_shots",
    "opponent_avg_inside_box_shots_conceded": "fixture_team_stats.shots_inside_box",
    "opponent_avg_outside_box_shots_conceded": "fixture_team_stats.shots_outside_box",
    "opponent_avg_blocked_shots_conceded": "fixture_team_stats.blocked_shots",
    "opponent_defensive_trend_recent": "fixture_team_stats.shots_on_target",
}

DEFENSIVE_INTERNAL_WEIGHTS: dict[str, float] = {
    "opponent_avg_sot_conceded": 0.35,
    "opponent_avg_total_shots_conceded": 0.22,
    "opponent_avg_inside_box_shots_conceded": 0.18,
    "opponent_avg_outside_box_shots_conceded": 0.07,
    "opponent_avg_blocked_shots_conceded": 0.06,
    "opponent_defensive_trend_recent": 0.12,
}
COMPONENT_KEY_DEFENSIVE = "opponent_defensive_resistance_component"
COMPONENT_LABEL_DEFENSIVE = "Resistenza difensiva avversaria"
