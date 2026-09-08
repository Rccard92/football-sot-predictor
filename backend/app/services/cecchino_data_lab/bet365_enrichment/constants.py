"""Costanti mapping quote Bet365 enrichment (solo *_last_seen)."""

from __future__ import annotations

from datetime import timedelta

# Tolleranza kickoff: +/- 2 ore
KICKOFF_TOLERANCE = timedelta(hours=2)
KICKOFF_TOLERANCE_MINUTES = 120

# Alias Discovery V2 — kickoff profile / bootstrap
KICKOFF_PROFILE_MIN_SAMPLES = 5
KICKOFF_PROFILE_MIN_MODAL_SHARE = 0.80
KICKOFF_CALIBRATED_TOLERANCE_MINUTES = 10
ALIAS_V2_MIN_DISTINCT_FIXTURES = 3
ALIAS_V2_MIN_DISTINCT_DATES = 2
ALIAS_V2_MAX_BOOTSTRAP_ITERATIONS = 10

MATCH_STATUS_EXACT = "EXACT"
MATCH_STATUS_SAFE_ALIAS = "SAFE_ALIAS"
MATCH_STATUS_AMBIGUOUS = "AMBIGUOUS"
MATCH_STATUS_NOT_FOUND = "NOT_FOUND"

MATCHED_STATUSES = frozenset({MATCH_STATUS_EXACT, MATCH_STATUS_SAFE_ALIAS})

RULE_EXACT_NORMALIZED = "exact_normalized"
RULE_SAFE_ALIAS = "safe_alias"
RULE_TEMP_ALIAS = "temp_alias"
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

# Prepare-apply cell actions (auditabili nel plan CSV)
CELL_ACTION_WOULD_WRITE = "WOULD_WRITE"
CELL_ACTION_ALREADY_SAME = "ALREADY_SAME"
CELL_ACTION_CONFLICT = "CONFLICT"
CELL_ACTION_NO_SOURCE_VALUE = "NO_SOURCE_VALUE"
CELL_ACTION_INVALID_SOURCE_VALUE = "INVALID_SOURCE_VALUE"

CELL_ACTIONS = frozenset(
    {
        CELL_ACTION_WOULD_WRITE,
        CELL_ACTION_ALREADY_SAME,
        CELL_ACTION_CONFLICT,
        CELL_ACTION_NO_SOURCE_VALUE,
        CELL_ACTION_INVALID_SOURCE_VALUE,
    }
)

# Chunk size for SELECT enrichment odds by lab_match_id
ENRICHMENT_ODDS_SELECT_CHUNK_SIZE = 2000

APPLY_PLAN_IDENTITY_COLUMNS: tuple[str, ...] = (
    "source_match_id",
    "lab_match_id",
    "competition",
    "season",
    "csv_home_team",
    "csv_away_team",
    "db_home_team",
    "db_away_team",
    "matching_status",
    "matching_rule",
)

APPLY_PLAN_CSV_FILENAME = "bet365_enrichment_apply_plan.csv"
APPLY_PLAN_SUMMARY_FILENAME = "bet365_enrichment_apply_summary.json"
PRE_APPLY_STATE_CSV_FILENAME = "bet365_enrichment_pre_apply_state.csv"
APPLY_RESULT_JSON_FILENAME = "bet365_enrichment_apply_result.json"

# Apply: lock chunk (SELECT FOR UPDATE); update chunk = executemany batch size
APPLY_LOCK_CHUNK_SIZE = 500
APPLY_UPDATE_CHUNK_SIZE = 1000

# Colonne Bet365 legacy: mai scrivibili da apply enrichment
LEGACY_BET365_COLUMNS: frozenset[str] = frozenset(
    {
        "bet365_home",
        "bet365_draw",
        "bet365_away",
        "bet365_over_25",
        "bet365_under_25",
        "bet365_ah_home",
        "bet365_ah_away",
        "asian_handicap_home_line",
        "bet365_closing_home",
        "bet365_closing_draw",
        "bet365_closing_away",
        "bet365_closing_over_25",
        "bet365_closing_under_25",
        "bet365_closing_ah_home",
        "bet365_closing_ah_away",
        "asian_handicap_closing_home_line",
    }
)

# Conteggio manifest: ricalcolati dal plan CSV e confrontati col summary
APPLY_MANIFEST_COUNT_KEYS: tuple[str, ...] = (
    "plan_rows",
    "duplicate_source_match_ids",
    "duplicate_lab_match_ids",
    "would_update_rows",
    "would_update_cells",
    "already_same_cells",
    "no_source_value_cells",
    "conflict_cells",
    "invalid_source_value_cells",
)
