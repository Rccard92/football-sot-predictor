"""Costanti Backtest Engine (Step B — nessun runtime collegato)."""

from __future__ import annotations

BACKTEST_MARKET_SHOTS_ON_TARGET = "shots_on_target"

BACKTEST_STATUS_PENDING = "pending"
BACKTEST_STATUS_RUNNING = "running"
BACKTEST_STATUS_COMPLETED = "completed"
BACKTEST_STATUS_PARTIAL_COMPLETED = "partial_completed"
BACKTEST_STATUS_FAILED = "failed"
BACKTEST_STATUS_CANCELLED = "cancelled"

BACKTEST_MODE_PRE_LINEUP = "pre_lineup"
BACKTEST_MODE_POST_LINEUP = "post_lineup"
BACKTEST_MODE_HISTORICAL_OFFICIAL_XI = "historical_official_xi"

BACKTEST_FIXTURE_SCOPE_FULL_SEASON = "full_season"
BACKTEST_FIXTURE_SCOPE_ROUND_RANGE = "round_range"
BACKTEST_FIXTURE_SCOPE_CUSTOM_RANGE = "custom_range"

PREDICTION_SCOPE_MATCH_TOTAL = "match_total"
PREDICTION_SCOPE_HOME_TEAM = "home_team"
PREDICTION_SCOPE_AWAY_TEAM = "away_team"

SIDE_MATCH_TOTAL = "match_total"
SIDE_HOME = "home"
SIDE_AWAY = "away"

BET_TYPE_OVER_UNDER_TOTAL = "over_under_total"
BET_TYPE_TEAM_OVER_UNDER = "team_over_under"

PICK_SIDE_OVER = "over"
PICK_SIDE_UNDER = "under"

PICK_RESULT_WON = "won"
PICK_RESULT_LOST = "lost"
PICK_RESULT_VOID = "void"
PICK_RESULT_PENDING = "pending"

BACKTEST_STATUSES: frozenset[str] = frozenset(
    {
        BACKTEST_STATUS_PENDING,
        BACKTEST_STATUS_RUNNING,
        BACKTEST_STATUS_COMPLETED,
        BACKTEST_STATUS_PARTIAL_COMPLETED,
        BACKTEST_STATUS_FAILED,
        BACKTEST_STATUS_CANCELLED,
    }
)

BACKTEST_MODES: frozenset[str] = frozenset(
    {
        BACKTEST_MODE_PRE_LINEUP,
        BACKTEST_MODE_POST_LINEUP,
        BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
    }
)

BACKTEST_FIXTURE_SCOPES: frozenset[str] = frozenset(
    {
        BACKTEST_FIXTURE_SCOPE_FULL_SEASON,
        BACKTEST_FIXTURE_SCOPE_ROUND_RANGE,
        BACKTEST_FIXTURE_SCOPE_CUSTOM_RANGE,
    }
)

PREDICTION_SCOPES: frozenset[str] = frozenset(
    {
        PREDICTION_SCOPE_MATCH_TOTAL,
        PREDICTION_SCOPE_HOME_TEAM,
        PREDICTION_SCOPE_AWAY_TEAM,
    }
)

SIDES: frozenset[str] = frozenset(
    {
        SIDE_MATCH_TOTAL,
        SIDE_HOME,
        SIDE_AWAY,
    }
)

BET_TYPES: frozenset[str] = frozenset(
    {
        BET_TYPE_OVER_UNDER_TOTAL,
        BET_TYPE_TEAM_OVER_UNDER,
    }
)

PICK_SIDES: frozenset[str] = frozenset(
    {
        PICK_SIDE_OVER,
        PICK_SIDE_UNDER,
    }
)

PICK_RESULTS: frozenset[str] = frozenset(
    {
        PICK_RESULT_WON,
        PICK_RESULT_LOST,
        PICK_RESULT_VOID,
        PICK_RESULT_PENDING,
    }
)

# Regole cross-field (enforcement a livello service futuro):
# prediction_scope = match_total → team_id NULL, side = match_total
# prediction_scope = home_team   → team_id valorizzato, side = home
# prediction_scope = away_team   → team_id valorizzato, side = away
