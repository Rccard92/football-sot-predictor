"""Costanti condivise (dominio calcio / ingestion)."""

from __future__ import annotations

from datetime import datetime, timezone

FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})

# Short status API-Football: partite non ancora giocate (pianificazione)
SCHEDULED_STATUSES = frozenset({"NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO"})

# Partite escluse da feature/prediction "prossime" (annullate / non giocabili)
UPCOMING_EXCLUDED_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})


def fixture_eligible_for_upcoming_sot(fixture_status: str, kickoff_at: datetime) -> bool:
    """
    True se la fixture può essere trattata come "prossima" per SOT pre-match.
    NS/TBD sempre; altri stati non conclusi solo se kickoff futuro (UTC).
    """
    st = (fixture_status or "").strip().upper()
    if st in FINISHED_STATUSES or st in UPCOMING_EXCLUDED_STATUSES:
        return False
    if st in ("NS", "TBD"):
        return True
    ko = kickoff_at
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return ko >= datetime.now(timezone.utc)

MIN_PRIOR_MATCHES_FOR_TEAM_AVG = 3

SOT_FEATURE_SET_VERSION = "sot-v2"

BASELINE_SOT_MODEL_VERSION = "baseline_v0_1"
BASELINE_SOT_MODEL_VERSION_V02 = "baseline_v0_2_context_player"
BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED = "baseline_v0_2_player_adjusted"
