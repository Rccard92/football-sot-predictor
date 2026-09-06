"""Costanti mapping quote Bet365 enrichment (solo *_last_seen)."""

from __future__ import annotations

from datetime import timedelta

# Tolleranza kickoff: +/- 2 ore
KICKOFF_TOLERANCE = timedelta(hours=2)
KICKOFF_TOLERANCE_MINUTES = 120

MATCH_STATUS_EXACT = "EXACT"
MATCH_STATUS_SAFE_ALIAS = "SAFE_ALIAS"
MATCH_STATUS_AMBIGUOUS = "AMBIGUOUS"
MATCH_STATUS_NOT_FOUND = "NOT_FOUND"

MATCHED_STATUSES = frozenset({MATCH_STATUS_EXACT, MATCH_STATUS_SAFE_ALIAS})

RULE_EXACT_NORMALIZED = "exact_normalized"
RULE_SAFE_ALIAS = "safe_alias"
RULE_AMBIGUOUS = "ambiguous"
RULE_NOT_FOUND = "not_found"

# CSV column -> CecchinoLabMatch attribute (last_seen only; never *_opening)
LAST_SEEN_ODDS_MAP: dict[str, str] = {
    "dc_1x_last_seen": "bet365_dc_1x",
    "dc_12_last_seen": "bet365_dc_12",
    "dc_x2_last_seen": "bet365_dc_x2",
    "ou_0_5_over_last_seen": "bet365_over_05",
    "ou_0_5_under_last_seen": "bet365_under_05",
    "ou_1_5_over_last_seen": "bet365_over_15",
    "ou_1_5_under_last_seen": "bet365_under_15",
    "ou_3_5_over_last_seen": "bet365_over_35",
    "ou_3_5_under_last_seen": "bet365_under_35",
    "ht_1_last_seen": "bet365_ht_home",
    "ht_x_last_seen": "bet365_ht_draw",
    "ht_2_last_seen": "bet365_ht_away",
}

ENRICHMENT_MODEL_FIELDS: tuple[str, ...] = tuple(LAST_SEEN_ODDS_MAP.values())

CSV_IDENTITY_COLUMNS: tuple[str, ...] = (
    "source_match_id",
    "competition_name",
    "competition_api_name",
    "season",
    "season_start_year",
    "kickoff_utc",
    "home_team",
    "away_team",
    "bookmaker",
)

BOOKMAKER_BET365 = "bet365"
