"""Metadati Player layer / Impatto giocatori (v1.1 Stage 6 + 7B lineup-adjusted)."""

from __future__ import annotations

COMPONENT_KEY_PLAYER = "player_layer_component"
COMPONENT_LABEL_PLAYER = "Player layer / Impatto giocatori"
PLAYER_LAYER_MODE_HISTORICAL = "historical_recent_profile"
PLAYER_LAYER_MODE_LINEUP = "lineup_adjusted"
PLAYER_LAYER_MODE = PLAYER_LAYER_MODE_HISTORICAL

PLAYER_NUMERIC_INPUT_ORDER: tuple[str, ...] = (
    "top_players_sot_per90_signal",
    "top_players_shots_per90_signal",
    "top_players_sot_share_signal",
    "top_players_shots_share_signal",
    "top_players_recent_minutes_signal",
    "top_players_rating_signal",
    "top_players_reliability_signal",
)

LINEUP_NUMERIC_INPUT_ORDER: tuple[str, ...] = (
    "starters_sot_per90_signal",
    "starters_shots_per90_signal",
    "starters_sot_share_signal",
    "starters_shots_share_signal",
    "starters_recent_minutes_signal",
    "starters_rating_signal",
    "starters_reliability_signal",
    "top_shooter_starter_presence_signal",
    "top_shooter_lineup_absence_signal",
)

PLAYER_LINEUP_CONTEXT_INPUT_ORDER: tuple[str, ...] = (
    "top_shooter_starter_presence_signal",
    "top_shooter_lineup_absence_signal",
)

PLAYER_CONTEXT_INPUT_ORDER: tuple[str, ...] = PLAYER_LINEUP_CONTEXT_INPUT_ORDER

PLAYER_INPUT_ORDER: tuple[str, ...] = PLAYER_NUMERIC_INPUT_ORDER + PLAYER_LINEUP_CONTEXT_INPUT_ORDER

PLAYER_INPUT_LABELS: dict[str, str] = {
    "top_players_sot_per90_signal": "Tiri in porta per 90 dei top player",
    "top_players_shots_per90_signal": "Tiri totali per 90 dei top player",
    "top_players_sot_share_signal": "Quota SOT squadra prodotta dai top player",
    "top_players_shots_share_signal": "Quota tiri squadra prodotta dai top player",
    "top_players_recent_minutes_signal": "Minuti recenti dei top player",
    "top_players_rating_signal": "Rating medio top player",
    "top_players_reliability_signal": "Affidabilità profili top player",
    "starters_sot_per90_signal": "Tiri in porta per 90 dei titolari",
    "starters_shots_per90_signal": "Tiri totali per 90 dei titolari",
    "starters_sot_share_signal": "Quota SOT squadra dei titolari",
    "starters_shots_share_signal": "Quota tiri squadra dei titolari",
    "starters_recent_minutes_signal": "Minuti recenti dei titolari",
    "starters_rating_signal": "Rating medio titolari",
    "starters_reliability_signal": "Affidabilità profili titolari",
    "top_shooter_starter_presence_signal": "Presenza top shooter titolari",
    "top_shooter_lineup_absence_signal": "Top shooter non titolari / non in distinta",
}

PLAYER_INPUT_SOURCE_PATHS: dict[str, str] = {
    "top_players_sot_per90_signal": "player_season_profiles.shots_on_per90",
    "top_players_shots_per90_signal": "player_season_profiles.shots_total_per90",
    "top_players_sot_share_signal": "player_season_profiles.team_sot_share",
    "top_players_shots_share_signal": "player_season_profiles.team_shots_share",
    "top_players_recent_minutes_signal": "player_season_profiles.recent_minutes_last5",
    "top_players_rating_signal": "player_season_profiles.avg_rating",
    "top_players_reliability_signal": "player_season_profiles.reliability_score",
    "starters_sot_per90_signal": "fixture_lineup_players + player_season_profiles.shots_on_per90",
    "starters_shots_per90_signal": "fixture_lineup_players + player_season_profiles.shots_total_per90",
    "starters_sot_share_signal": "fixture_lineup_players + player_season_profiles.team_sot_share",
    "starters_shots_share_signal": "fixture_lineup_players + player_season_profiles.team_shots_share",
    "starters_recent_minutes_signal": "fixture_lineup_players + player_season_profiles.recent_minutes_last5",
    "starters_rating_signal": "fixture_lineup_players + player_season_profiles.avg_rating",
    "starters_reliability_signal": "fixture_lineup_players + player_season_profiles.reliability_score",
    "top_shooter_starter_presence_signal": "fixture_lineups + fixture_lineup_players + player_season_profiles",
    "top_shooter_lineup_absence_signal": "fixture_lineups + fixture_lineup_players + player_season_profiles",
}

PLAYER_INPUT_API_SOURCES: dict[str, str] = {
    k: (
        "fixture_lineups"
        if k.startswith("starters_") or k.startswith("top_shooter_")
        else "player_season_profiles"
    )
    for k in PLAYER_INPUT_LABELS
}
PLAYER_INPUT_DB_FIELDS: dict[str, str] = {k: PLAYER_INPUT_SOURCE_PATHS[k] for k in PLAYER_INPUT_LABELS}

PLAYER_INTERNAL_WEIGHTS: dict[str, float] = {
    "top_players_sot_per90_signal": 0.28,
    "top_players_shots_per90_signal": 0.18,
    "top_players_sot_share_signal": 0.18,
    "top_players_shots_share_signal": 0.10,
    "top_players_recent_minutes_signal": 0.12,
    "top_players_rating_signal": 0.08,
    "top_players_reliability_signal": 0.06,
}

LINEUP_INTERNAL_WEIGHTS: dict[str, float] = {
    "starters_sot_per90_signal": 0.23,
    "starters_shots_per90_signal": 0.15,
    "starters_sot_share_signal": 0.15,
    "starters_shots_share_signal": 0.08,
    "starters_recent_minutes_signal": 0.10,
    "starters_rating_signal": 0.07,
    "starters_reliability_signal": 0.05,
    "top_shooter_starter_presence_signal": 0.12,
    "top_shooter_lineup_absence_signal": 0.05,
}

REQUIRED_LEAGUE_PLAYER_KEYS: tuple[str, ...] = (
    "league_top_players_avg_sot_per90",
    "league_top_players_avg_shots_per90",
    "league_top_players_avg_sot_share",
    "league_top_players_avg_shots_share",
    "league_top_players_recent_minutes",
    "league_top_players_avg_rating",
    "league_top_players_reliability",
)

LEAGUE_PLAYER_BASELINE_FIELD_MAP: dict[str, str] = {
    "top_players_sot_per90_signal": "league_top_players_avg_sot_per90",
    "top_players_shots_per90_signal": "league_top_players_avg_shots_per90",
    "top_players_sot_share_signal": "league_top_players_avg_sot_share",
    "top_players_shots_share_signal": "league_top_players_avg_shots_share",
    "top_players_recent_minutes_signal": "league_top_players_recent_minutes",
    "top_players_rating_signal": "league_top_players_avg_rating",
    "top_players_reliability_signal": "league_top_players_reliability",
}

LINEUP_LEAGUE_BASELINE_FIELD_MAP: dict[str, str] = {
    "starters_sot_per90_signal": "league_top_players_avg_sot_per90",
    "starters_shots_per90_signal": "league_top_players_avg_shots_per90",
    "starters_sot_share_signal": "league_top_players_avg_sot_share",
    "starters_shots_share_signal": "league_top_players_avg_shots_share",
    "starters_recent_minutes_signal": "league_top_players_recent_minutes",
    "starters_rating_signal": "league_top_players_avg_rating",
    "starters_reliability_signal": "league_top_players_reliability",
}

LINEUP_STARTER_SIGNAL_FIELDS: dict[str, str] = {
    "starters_sot_per90_signal": "shots_on_per90",
    "starters_shots_per90_signal": "shots_total_per90",
    "starters_sot_share_signal": "team_sot_share",
    "starters_shots_share_signal": "team_shots_share",
    "starters_recent_minutes_signal": "recent_minutes_last5",
    "starters_rating_signal": "avg_rating",
    "starters_reliability_signal": "reliability_score",
}

TOP_SHOOTER_ABSENCE_AUDIT_NOTE = (
    "Questo dato deriva dalle formazioni ufficiali. Non distingue ancora infortunio/squalifica: "
    "questa informazione verrà completata con injuries/sidelined."
)
