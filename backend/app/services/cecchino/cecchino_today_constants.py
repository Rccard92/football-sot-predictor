"""Costanti Cecchino Today discovery."""

from __future__ import annotations

CECCHINO_TODAY_VERSION = "cecchino_today_v0_13_api_gates"
DEFAULT_TODAY_TIMEZONE = "Europe/Rome"
DEFAULT_RETENTION_DAYS = 7
TIMELINE_WINDOW_DAYS = 7
PROVIDER_API_FOOTBALL = "api_football"

MIN_HOME_CONTEXT = 3
MIN_AWAY_CONTEXT = 3
MIN_HOME_TOTAL = 6
MIN_AWAY_TOTAL = 6
MIN_RECENT_CONTEXT_5 = 3
MIN_RECENT_TOTAL_6 = 5

WOMEN_KEYWORDS = frozenset(
    {
        "women",
        "woman",
        "female",
        "femminile",
        "féminin",
        "frauen",
        "mujeres",
        "feminino",
        "femenil",
        "w-league",
        "w league",
    },
)

CUP_KEYWORDS = frozenset(
    {
        "cup",
        "coppa",
        "copa",
        "coupe",
        "pokal",
        "trophy",
        "super cup",
        "supercup",
        "shield",
        "champions league",
        "europa league",
        "conference league",
        "libertadores",
        "sudamericana",
        "fa cup",
        "league cup",
        "carabao",
        "copa del rey",
        "dfb pokal",
        "coppa italia",
    },
)

FRIENDLY_KEYWORDS = frozenset(
    {
        "friendly",
        "friendlies",
        "amichevole",
        "club friendly",
    },
)

YOUTH_KEYWORDS = frozenset(
    {
        "u17",
        "u18",
        "u19",
        "u20",
        "u21",
        "youth",
        "primavera",
        "reserve",
        "reserves",
    },
)
