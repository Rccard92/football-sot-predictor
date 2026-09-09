"""Costanti riconciliazione stats BLOCCO 2 da raw_json (solo audit/dry-run).

ANTI-LEAKAGE (documentazione, non wiring predittivo):
- HS/AS, HST/AST, HF/AF, HC/AC, HY/AY, HR/AR, FTHG/FTAG/FTR, HTHG/HTAG/HTR
  descrivono il match DOPO il fischio finale. Non sono feature pre-match della
  stessa partita: solo label della partita corrente oppure storico per match
  cronologicamente successivi.
- Referee è metadata potenzialmente conoscibile pre-match, ma in questo task
  NON viene integrato nel motore predittivo / KPI / buyability / Pattern Lab.
- Questo package non tocca quote Bet365 né mercati CORE BLOCCO 1.
"""

from __future__ import annotations

# raw_json CSV key -> colonna tipizzata CecchinoLabMatch
RAW_TO_DB_FIELD_MAP: dict[str, str] = {
    "Referee": "referee",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HC": "home_corners",
    "AC": "away_corners",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
    "HTHG": "ht_home_goals",
    "HTAG": "ht_away_goals",
    "HTR": "ht_result",
    "FTHG": "ft_home_goals",
    "FTAG": "ft_away_goals",
    "FTR": "ft_result",
}

STATS_MODEL_FIELDS: tuple[str, ...] = tuple(RAW_TO_DB_FIELD_MAP.values())

DB_TO_RAW_FIELD_MAP: dict[str, str] = {v: k for k, v in RAW_TO_DB_FIELD_MAP.items()}

# Tipi di valore attesi dopo parse
STRING_FIELDS: frozenset[str] = frozenset({"referee", "ht_result", "ft_result"})
INT_FIELDS: frozenset[str] = frozenset(STATS_MODEL_FIELDS) - STRING_FIELDS

# Gruppi coverage (tutti i campi del gruppo devono soddisfare la condizione)
COVERAGE_GROUPS: dict[str, tuple[str, ...]] = {
    "referee": ("referee",),
    "shots": ("home_shots", "away_shots"),
    "shots_on_target": ("home_shots_on_target", "away_shots_on_target"),
    "fouls": ("home_fouls", "away_fouls"),
    "corners": ("home_corners", "away_corners"),
    "yellow_cards": ("home_yellow_cards", "away_yellow_cards"),
    "red_cards": ("home_red_cards", "away_red_cards"),
    "halftime": ("ht_home_goals", "ht_away_goals", "ht_result"),
    "fulltime": ("ft_home_goals", "ft_away_goals", "ft_result"),
}

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

# Source disponibile = non NO_SOURCE e non INVALID
SOURCE_AVAILABLE_ACTIONS = frozenset(
    {
        CELL_ACTION_WOULD_WRITE,
        CELL_ACTION_ALREADY_SAME,
        CELL_ACTION_CONFLICT,
    }
)

MATCH_STATUS_HAS_RAW = "HAS_RAW"
MATCH_STATUS_NO_RAW = "NO_RAW"

SUMMARY_FILENAME = "stats_raw_reconciliation_summary.json"
AUDIT_CSV_FILENAME = "stats_raw_reconciliation_audit.csv"

AUDIT_COLUMNS: tuple[str, ...] = (
    "source_file",
    "source_row",
    "lab_match_id",
    "competition",
    "season",
    "kickoff",
    "home_team",
    "away_team",
    "match_status",
    "field",
    "source_value",
    "db_value",
    "action",
)
