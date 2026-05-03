"""Tabelle attese dallo schema applicativo (allineate ai modelli SQLAlchemy)."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "leagues",
        "seasons",
        "teams",
        "players",
        "fixtures",
        "fixture_team_stats",
        "fixture_player_stats",
        "fixture_lineups",
        "ingestion_runs",
        "team_sot_features",
        "team_sot_predictions",
        "prediction_backtests",
    },
)


def get_existing_table_names(engine: Engine) -> set[str]:
    insp = inspect(engine)
    dialect = engine.dialect.name
    if dialect == "postgresql":
        return set(insp.get_table_names(schema="public"))
    return set(insp.get_table_names())
