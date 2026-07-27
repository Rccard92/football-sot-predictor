"""Costanti Cecchino Lab — Football-Data UK + Bet365."""

from __future__ import annotations

PARSER_VERSION = "football_data_uk_bet365_v2"
SOURCE_PROVIDER = "football-data.co.uk"
IMPORT_CONFIRM_TOKEN = "IMPORT_CECCHINO_LAB_CSV"
REPLACE_CONFIRM_TOKEN = "REPLACE_CECCHINO_LAB_DATASET"
HISTORICAL_SCAN_CONFIRM_TOKEN = "RUN_CECCHINO_LAB_HISTORICAL_SCAN"
HISTORICAL_SCAN_VERSION = "cecchino_lab_historical_scan_v3"
HISTORICAL_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION = 20
HISTORICAL_PILOT_STRATEGY_MAX_MATCHES = "max_matches"
HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP = "eligible_per_competition"
HISTORICAL_KPI_VERSION = "cecchino_lab_kpi_bet365_v1"
HISTORICAL_QUOTE_POLICY_VERSION = "bet365_closing_pre_fallback_v1"
HISTORICAL_DERIVATION_METHOD = "normalized_fair_probability_from_bet365_1x2"
DEFAULT_HISTORICAL_SEASON = "2021/2022"
RAW_EXTRA_COLUMNS_KEY = "__extra_columns__"
SCAN_BATCH_SIZE = 25

# Limiti import multiplo (batch preview)
BATCH_MAX_FILES = 20
BATCH_MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB
BATCH_PREVIEW_ROWS = 5
BATCH_ISSUES_CAP = 30

# Colonne canoniche Football-Data (obbligatorie per un CSV valido)
REQUIRED_HEADERS = frozenset({"Div", "Date", "HomeTeam", "AwayTeam"})

# Colonne risultato / stats riconosciute
KNOWN_RESULT_HEADERS = frozenset(
    {
        "Div",
        "Date",
        "Time",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
        "HTHG",
        "HTAG",
        "HTR",
        "Referee",
        "HS",
        "AS",
        "HST",
        "AST",
        "HF",
        "AF",
        "HC",
        "AC",
        "HY",
        "AY",
        "HR",
        "AR",
    }
)

# Mappa colonna CSV → campo modello (solo Bet365)
BET365_COLUMN_MAP: dict[str, str] = {
    "B365H": "bet365_home",
    "B365D": "bet365_draw",
    "B365A": "bet365_away",
    "B365CH": "bet365_closing_home",
    "B365CD": "bet365_closing_draw",
    "B365CA": "bet365_closing_away",
    "B365>2.5": "bet365_over_25",
    "B365<2.5": "bet365_under_25",
    "B365C>2.5": "bet365_closing_over_25",
    "B365C<2.5": "bet365_closing_under_25",
    "AHh": "asian_handicap_home_line",
    "B365AHH": "bet365_ah_home",
    "B365AHA": "bet365_ah_away",
    "AHCh": "asian_handicap_closing_home_line",
    "B365CAHH": "bet365_closing_ah_home",
    "B365CAHA": "bet365_closing_ah_away",
}

BET365_HEADERS = frozenset(BET365_COLUMN_MAP.keys())

ALL_KNOWN_HEADERS = KNOWN_RESULT_HEADERS | BET365_HEADERS

# Issue codes
ISSUE_EMPTY_FILE = "empty_file"
ISSUE_INVALID_HEADER = "invalid_header"
ISSUE_MISSING_DIVISION = "missing_division"
ISSUE_INVALID_DATE = "invalid_date"
ISSUE_INVALID_TIME = "invalid_time"
ISSUE_MISSING_HOME_TEAM = "missing_home_team"
ISSUE_MISSING_AWAY_TEAM = "missing_away_team"
ISSUE_SAME_TEAM = "same_team_home_away"
ISSUE_FT_RESULT_INCONSISTENT = "ft_result_inconsistent"
ISSUE_HT_RESULT_INCONSISTENT = "ht_result_inconsistent"
ISSUE_ODDS_LTE_ONE = "odds_lte_one"
ISSUE_AH_LINE_NOT_QUARTER = "ah_line_not_quarter"
ISSUE_COLUMN_COUNT_MISMATCH = "column_count_mismatch"
ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS = "uniform_extra_trailing_columns"
ISSUE_IRREGULAR_COLUMN_COUNT = "irregular_column_count"
ISSUE_DUPLICATE_MATCH = "duplicate_match"
ISSUE_PARTIAL_STATISTICS = "partial_statistics"
ISSUE_PARTIAL_BET365 = "partial_bet365"
ISSUE_PARTIAL_BET365_AH = "partial_bet365_ah"
ISSUE_DIVISION_MISMATCH = "division_mismatch"
ISSUE_UNEXPECTED_COLUMNS = "unexpected_columns"
ISSUE_ROW_ERROR = "row_error"
