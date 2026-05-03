"""Costanti condivise (dominio calcio / ingestion)."""

FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})

# Short status API-Football: partite non ancora giocate (pianificazione)
SCHEDULED_STATUSES = frozenset({"NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO"})

MIN_PRIOR_MATCHES_FOR_TEAM_AVG = 3

SOT_FEATURE_SET_VERSION = "sot-v1"

BASELINE_SOT_MODEL_VERSION = "baseline_v0_1"
