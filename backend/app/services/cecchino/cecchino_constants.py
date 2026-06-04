"""Costanti Cecchino (indipendenti da model_version SOT)."""

from __future__ import annotations

CECCHINO_VERSION = "cecchino_v0_1_excel_parity"

PICCHETTO_KEY_HOME_AWAY = "home_away"
PICCHETTO_KEY_TOTALS = "totals"
PICCHETTO_KEY_LAST5_HOME_AWAY = "last5_home_away"
PICCHETTO_KEY_LAST6_TOTALS = "last6_totals"

FINAL_QUOTA_WEIGHTS: dict[str, float] = {
    PICCHETTO_KEY_HOME_AWAY: 0.20,
    PICCHETTO_KEY_TOTALS: 0.25,
    PICCHETTO_KEY_LAST5_HOME_AWAY: 0.20,
    PICCHETTO_KEY_LAST6_TOTALS: 0.35,
}

STATUS_AVAILABLE = "available"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_ERROR = "error"
STATUS_PENDING_FORMULA = "pending_formula_extraction"

WARNING_ZERO_MATCHES = "zero_matches_in_context"
WARNING_ZERO_PROBABILITY = "zero_probability"
WARNING_PARTIAL_RECENT_SAMPLE = "partial_recent_sample"

PLACEHOLDER_SIGNALS = {"status": STATUS_PENDING_FORMULA}
PLACEHOLDER_RELIABILITY = {"status": "not_implemented_yet"}
PLACEHOLDER_BOOKMAKER = {"status": "not_implemented_yet"}
