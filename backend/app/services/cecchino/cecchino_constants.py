"""Costanti Cecchino (indipendenti da model_version SOT)."""

from __future__ import annotations

CECCHINO_VERSION = "cecchino_v0_2_real_records"

PICCHETTO_KEY_HOME_AWAY = "home_away"
PICCHETTO_KEY_TOTALS = "totals"
PICCHETTO_KEY_LAST5_HOME_AWAY = "last5_home_away"
PICCHETTO_KEY_LAST6_TOTALS = "last6_totals"

# Chiavi contesto dati (8 slice)
KEY_HOME_CONTEXT = "home_context"
KEY_AWAY_CONTEXT = "away_context"
KEY_HOME_TOTAL = "home_total"
KEY_AWAY_TOTAL = "away_total"
KEY_HOME_RECENT_CONTEXT_5 = "home_recent_context_5"
KEY_AWAY_RECENT_CONTEXT_5 = "away_recent_context_5"
KEY_HOME_RECENT_TOTAL_6 = "home_recent_total_6"
KEY_AWAY_RECENT_TOTAL_6 = "away_recent_total_6"

INPUT_SNAPSHOT_CONTEXT_KEYS: tuple[str, ...] = (
    KEY_HOME_CONTEXT,
    KEY_AWAY_CONTEXT,
    KEY_HOME_TOTAL,
    KEY_AWAY_TOTAL,
    KEY_HOME_RECENT_CONTEXT_5,
    KEY_AWAY_RECENT_CONTEXT_5,
    KEY_HOME_RECENT_TOTAL_6,
    KEY_AWAY_RECENT_TOTAL_6,
)

CONTEXT_SLICE_LABELS: dict[str, str] = {
    KEY_HOME_CONTEXT: "Casa split casalinghe",
    KEY_AWAY_CONTEXT: "Trasferta split esterne",
    KEY_HOME_TOTAL: "Totali casa",
    KEY_AWAY_TOTAL: "Totali trasferta",
    KEY_HOME_RECENT_CONTEXT_5: "Ultime 5 casalinghe",
    KEY_AWAY_RECENT_CONTEXT_5: "Ultime 5 esterne",
    KEY_HOME_RECENT_TOTAL_6: "Ultime 6 totali casa",
    KEY_AWAY_RECENT_TOTAL_6: "Ultime 6 totali trasferta",
}

TARGET_RECENT_CONTEXT = 5
TARGET_RECENT_TOTAL = 6

FINAL_QUOTA_WEIGHTS: dict[str, float] = {
    PICCHETTO_KEY_HOME_AWAY: 0.20,
    PICCHETTO_KEY_TOTALS: 0.25,
    PICCHETTO_KEY_LAST5_HOME_AWAY: 0.20,
    PICCHETTO_KEY_LAST6_TOTALS: 0.35,
}

STATUS_AVAILABLE = "available"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_PARTIAL_LOW_SAMPLE = "partial_low_sample"
STATUS_ERROR = "error"
STATUS_PENDING_FORMULA = "pending_formula_extraction"

WARNING_ZERO_MATCHES = "zero_matches_in_context"
WARNING_ZERO_PROBABILITY = "zero_probability"
WARNING_PARTIAL_RECENT_SAMPLE = "partial_recent_sample"
WARNING_LOW_SAMPLE = "low_sample"

LEAKAGE_PASSED = "passed"
LEAKAGE_FAILED = "failed"
LEAKAGE_UNDEFINED = "undefined"

PLACEHOLDER_SIGNALS = {"status": STATUS_PENDING_FORMULA}
PLACEHOLDER_RELIABILITY = {"status": "not_implemented_yet"}
PLACEHOLDER_BOOKMAKER = {"status": "not_implemented_yet"}

# Picchetti utilizzabili per quota finale (incluso campione parziale)
PICCHETTO_STATUSES_FOR_FINAL = frozenset({STATUS_AVAILABLE, STATUS_PARTIAL_LOW_SAMPLE})
