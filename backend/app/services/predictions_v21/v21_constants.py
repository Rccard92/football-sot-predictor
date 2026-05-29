"""Costanti numeriche e chiavi formula v2.1."""

from __future__ import annotations

ANCHOR_TEAM_SOT_WEIGHT = 0.55
ANCHOR_OPP_SOT_CONCEDED_WEIGHT = 0.45

MICRO_NORM_MIN = 0.70
MICRO_NORM_MAX = 1.30
MACRO_INDEX_MIN = 0.75
MACRO_INDEX_MAX = 1.25
FINAL_MULTIPLIER_MIN = 0.75
FINAL_MULTIPLIER_MAX = 1.30

RECENT_FORM_MATCHES = 5
TOP_SHOOTERS_COUNT = 5

V21_ENGINE_STATUS_READY = "ready"
V21_ENGINE_STATUS_PARTIAL = "partial"
V21_ENGINE_STATUS_MANIFEST_INVALID = "manifest_invalid"

PREDICTIVE_MACRO_KEYS: tuple[str, ...] = (
    "offensive_production",
    "opponent_defensive_resistance",
    "home_away_split",
    "recent_form",
    "chance_quality",
    "player_layer",
    "lineups",
    "injuries_unavailable",
    "pace_control",
)

QUALITY_MACRO_KEY = "model_quality_controls"
