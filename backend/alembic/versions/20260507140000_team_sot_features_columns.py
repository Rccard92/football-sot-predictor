"""team_sot_features: colonne esplicite per feature SOT

Revision ID: 20260507140000
Revises: 20260506120000
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260507140000"
down_revision: Union[str, Sequence[str], None] = "20260506120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector: sa.Inspector, bind) -> set[str]:
    if bind.dialect.name == "postgresql":
        return set(inspector.get_table_names(schema="public"))
    return set(inspector.get_table_names())


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in _table_names(inspector, bind)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in _table_names(inspector, bind):
        return False
    col_kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    columns = [col["name"] for col in inspector.get_columns(table_name, **col_kw)]
    return column_name in columns


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_exists(table_name) and not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def drop_column_if_exists(table_name: str, column_name: str) -> None:
    if table_exists(table_name) and column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    add_column_if_missing(
        "team_sot_features",
        sa.Column("opponent_team_id", sa.BigInteger(), nullable=True),
    )
    add_column_if_missing(
        "team_sot_features",
        sa.Column("side", sa.String(length=8), nullable=True),
    )
    add_column_if_missing(
        "team_sot_features",
        sa.Column("fixture_date", sa.DateTime(timezone=True), nullable=True),
    )
    for col_name in (
        "season_avg_sot_for",
        "season_avg_sot_against",
        "home_away_avg_sot_for",
        "home_away_avg_sot_against",
        "last5_avg_sot_for",
        "last5_avg_sot_against",
        "last10_avg_sot_for",
        "last10_avg_sot_against",
        "opponent_season_avg_sot_conceded",
        "opponent_home_away_avg_sot_conceded",
        "opponent_last5_avg_sot_conceded",
    ):
        add_column_if_missing(
            "team_sot_features",
            sa.Column(col_name, sa.Numeric(14, 6), nullable=True),
        )
    add_column_if_missing("team_sot_features", sa.Column("rest_days", sa.Integer(), nullable=True))
    add_column_if_missing("team_sot_features", sa.Column("actual_sot", sa.Integer(), nullable=True))
    add_column_if_missing(
        "team_sot_features",
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    add_column_if_missing(
        "team_sot_features",
        sa.Column("previous_matches_count", sa.Integer(), nullable=True),
    )
    add_column_if_missing(
        "team_sot_features",
        sa.Column("opponent_previous_matches_count", sa.Integer(), nullable=True),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and table_exists("team_sot_features"):
        if column_exists("team_sot_features", "opponent_team_id"):
            op.execute(
                sa.text(
                    """
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'fk_team_sot_features_opponent_team'
                      ) THEN
                        ALTER TABLE team_sot_features
                          ADD CONSTRAINT fk_team_sot_features_opponent_team
                          FOREIGN KEY (opponent_team_id) REFERENCES teams(id) ON DELETE SET NULL;
                      END IF;
                    END $$;
                    """,
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and table_exists("team_sot_features"):
        op.execute(
            sa.text(
                """
                ALTER TABLE team_sot_features
                DROP CONSTRAINT IF EXISTS fk_team_sot_features_opponent_team;
                """,
            ),
        )
    drop_column_if_exists("team_sot_features", "opponent_previous_matches_count")
    drop_column_if_exists("team_sot_features", "previous_matches_count")
    drop_column_if_exists("team_sot_features", "fallback_used")
    drop_column_if_exists("team_sot_features", "actual_sot")
    drop_column_if_exists("team_sot_features", "rest_days")
    for col in (
        "opponent_last5_avg_sot_conceded",
        "opponent_home_away_avg_sot_conceded",
        "opponent_season_avg_sot_conceded",
        "last10_avg_sot_against",
        "last10_avg_sot_for",
        "last5_avg_sot_against",
        "last5_avg_sot_for",
        "home_away_avg_sot_against",
        "home_away_avg_sot_for",
        "season_avg_sot_against",
        "season_avg_sot_for",
    ):
        drop_column_if_exists("team_sot_features", col)
    drop_column_if_exists("team_sot_features", "fixture_date")
    drop_column_if_exists("team_sot_features", "side")
    drop_column_if_exists("team_sot_features", "opponent_team_id")
