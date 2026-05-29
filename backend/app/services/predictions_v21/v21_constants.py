"""Costanti numeriche e chiavi formula v2.1."""

from __future__ import annotations

ANCHOR_TEAM_SOT_WEIGHT = 0.55
ANCHOR_OPP_SOT_CONCEDED_WEIGHT = 0.45

MICRO_NORM_MIN = 0.70
MICRO_NORM_MAX = 1.30
XG_PRUDENT_ADJ_MIN = 0.85
XG_PRUDENT_ADJ_MAX = 1.15
MACRO_INDEX_MIN = 0.75
MACRO_INDEX_MAX = 1.25
FINAL_MULTIPLIER_MIN = 0.75
FINAL_MULTIPLIER_MAX = 1.30

RECENT_FORM_MATCHES = 5
TOP_SHOOTERS_COUNT = 5
LINEUP_HISTORY_MATCHES = 12
LINEUP_HISTORY_MIN_FIXTURES = 3

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

WEIGHT_SCALE_MANIFEST_POINTS = "manifest_points"


def format_weight_pct(macro_weight: int | float | None) -> str:
    """16 (punti manifest) → '16%'."""
    if macro_weight is None:
        return "—"
    w = float(macro_weight)
    if w <= 0:
        return "0%"
    if w <= 1.0:
        return f"{round(w * 100, 2):g}%"
    rounded = round(w, 2)
    return f"{int(rounded) if rounded == int(rounded) else rounded}%"
