"""Metadati input Qualità occasioni / xG (v1.1 Stage 5)."""

from __future__ import annotations

COMPONENT_KEY_XG = "xg_chance_quality_component"
COMPONENT_LABEL_XG = "Qualità occasioni / xG"

XG_INPUT_LABELS: dict[str, str] = {
    "avg_xg_for": "xG prodotti",
    "opponent_avg_xg_conceded": "xG concessi dall'avversario",
    "team_xg_delta_vs_league": "Delta xG squadra vs media lega",
    "opponent_xg_conceded_delta_vs_league": "Delta xG concesso avversario vs media lega",
    "xg_prudent_adjustment_signal": "xG adjustment prudente",
}

XG_INPUT_API_SOURCES: dict[str, str] = {
    "avg_xg_for": "fixtures/statistics::expected_goals",
    "opponent_avg_xg_conceded": "fixtures/statistics::expected_goals",
    "team_xg_delta_vs_league": "fixtures/statistics::expected_goals",
    "opponent_xg_conceded_delta_vs_league": "fixtures/statistics::expected_goals",
    "xg_prudent_adjustment_signal": "fixtures/statistics::expected_goals",
}

XG_INPUT_DB_FIELDS: dict[str, str] = {
    "avg_xg_for": "fixture_team_stats.expected_goals",
    "opponent_avg_xg_conceded": "fixture_team_stats.expected_goals",
    "team_xg_delta_vs_league": "fixture_team_stats.expected_goals",
    "opponent_xg_conceded_delta_vs_league": "fixture_team_stats.expected_goals",
    "xg_prudent_adjustment_signal": "fixture_team_stats.expected_goals",
}

XG_INPUT_SOURCE_PATHS: dict[str, str] = {
    "avg_xg_for": "fixture_team_stats.expected_goals (media partite squadra)",
    "opponent_avg_xg_conceded": "fixture_team_stats.expected_goals (avversari vs avversario)",
    "team_xg_delta_vs_league": "derived:avg_xg_for − league_avg_xg_for",
    "opponent_xg_conceded_delta_vs_league": "derived:opponent_avg_xg_conceded − league_avg_xg_conceded",
    "xg_prudent_adjustment_signal": "derived:league_avg_sot_for×(1+xg_adjustment_pct)",
}

XG_INTERNAL_WEIGHTS: dict[str, float] = {
    "avg_xg_for": 0.30,
    "opponent_avg_xg_conceded": 0.30,
    "team_xg_delta_vs_league": 0.15,
    "opponent_xg_conceded_delta_vs_league": 0.15,
    "xg_prudent_adjustment_signal": 0.10,
}

XG_INPUT_ORDER: tuple[str, ...] = tuple(XG_INTERNAL_WEIGHTS.keys())
