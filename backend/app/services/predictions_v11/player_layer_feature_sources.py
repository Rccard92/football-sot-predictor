"""Metadati Player layer / Impatto giocatori (v1.1 Stage 6)."""

from __future__ import annotations

COMPONENT_KEY_PLAYER = "player_layer_component"
COMPONENT_LABEL_PLAYER = "Player layer / Impatto giocatori"
PLAYER_LAYER_MODE = "historical_recent_profile"

PLAYER_NUMERIC_INPUT_ORDER: tuple[str, ...] = (
    "top_players_sot_per90_signal",
    "top_players_shots_per90_signal",
    "top_players_sot_share_signal",
    "top_players_shots_share_signal",
    "top_players_recent_minutes_signal",
    "top_players_rating_signal",
    "top_players_reliability_signal",
)

PLAYER_CONTEXT_INPUT_ORDER: tuple[str, ...] = (
    "top_shooter_presence_status",
    "top_shooter_absence_status",
)

PLAYER_INPUT_ORDER: tuple[str, ...] = PLAYER_NUMERIC_INPUT_ORDER + PLAYER_CONTEXT_INPUT_ORDER

PLAYER_INPUT_LABELS: dict[str, str] = {
    "top_players_sot_per90_signal": "Tiri in porta per 90 dei top player",
    "top_players_shots_per90_signal": "Tiri totali per 90 dei top player",
    "top_players_sot_share_signal": "Quota SOT squadra prodotta dai top player",
    "top_players_shots_share_signal": "Quota tiri squadra prodotta dai top player",
    "top_players_recent_minutes_signal": "Minuti recenti dei top player",
    "top_players_rating_signal": "Rating medio top player",
    "top_players_reliability_signal": "Affidabilità profili top player",
    "top_shooter_presence_status": "Presenza top shooter",
    "top_shooter_absence_status": "Assenza top shooter",
}

PLAYER_INPUT_SOURCE_PATHS: dict[str, str] = {
    "top_players_sot_per90_signal": "player_season_profiles.shots_on_per90",
    "top_players_shots_per90_signal": "player_season_profiles.shots_total_per90",
    "top_players_sot_share_signal": "player_season_profiles.team_sot_share",
    "top_players_shots_share_signal": "player_season_profiles.team_shots_share",
    "top_players_recent_minutes_signal": "player_season_profiles.recent_minutes_last5",
    "top_players_rating_signal": "player_season_profiles.avg_rating",
    "top_players_reliability_signal": "player_season_profiles.reliability_score",
    "top_shooter_presence_status": "lineups (non applicato in stage 6)",
    "top_shooter_absence_status": "injuries/lineups (non applicato in stage 6)",
}

PLAYER_INPUT_API_SOURCES: dict[str, str] = {k: "player_season_profiles" for k in PLAYER_INPUT_ORDER}
PLAYER_INPUT_DB_FIELDS: dict[str, str] = {k: PLAYER_INPUT_SOURCE_PATHS[k] for k in PLAYER_INPUT_ORDER}

PLAYER_INTERNAL_WEIGHTS: dict[str, float] = {
    "top_players_sot_per90_signal": 0.28,
    "top_players_shots_per90_signal": 0.18,
    "top_players_sot_share_signal": 0.18,
    "top_players_shots_share_signal": 0.10,
    "top_players_recent_minutes_signal": 0.12,
    "top_players_rating_signal": 0.08,
    "top_players_reliability_signal": 0.06,
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
