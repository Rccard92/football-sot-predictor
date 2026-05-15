"""Tabelle attese dallo schema applicativo (allineate ai modelli SQLAlchemy)."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "leagues",
        "seasons",
        "teams",
        "players",
        "player_registry",
        "player_team_seasons",
        "fixtures",
        "fixture_team_stats",
        "fixture_player_stats",
        "fixture_lineups",
        "ingestion_runs",
        "team_sot_features",
        "team_sot_predictions",
        "prediction_backtests",
        "player_sot_profiles",
        "player_availability_events",
        "player_match_stats",
        "player_season_profiles",
    },
)


def get_existing_table_names(engine: Engine) -> set[str]:
    insp = inspect(engine)
    dialect = engine.dialect.name
    if dialect == "postgresql":
        return set(insp.get_table_names(schema="public"))
    return set(insp.get_table_names())
