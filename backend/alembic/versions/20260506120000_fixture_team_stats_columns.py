"""fixture_team_stats extended columns for API-Football mapping

Revision ID: 20260506120000
Revises: 20260505120000
Create Date: 2026-05-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260506120000"
down_revision: Union[str, Sequence[str], None] = "20260505120000"
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
    add_column_if_missing("fixture_team_stats", sa.Column("side", sa.String(length=8), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("shots_off_target", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("total_shots", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("blocked_shots", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("shots_inside_box", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("shots_outside_box", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("fouls", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("corner_kicks", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("offsides", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("ball_possession_pct", sa.Double(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("yellow_cards", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("red_cards", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("goalkeeper_saves", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("total_passes", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("accurate_passes", sa.Integer(), nullable=True))
    add_column_if_missing("fixture_team_stats", sa.Column("pass_accuracy_pct", sa.Double(), nullable=True))


def downgrade() -> None:
    drop_column_if_exists("fixture_team_stats", "pass_accuracy_pct")
    drop_column_if_exists("fixture_team_stats", "accurate_passes")
    drop_column_if_exists("fixture_team_stats", "total_passes")
    drop_column_if_exists("fixture_team_stats", "goalkeeper_saves")
    drop_column_if_exists("fixture_team_stats", "red_cards")
    drop_column_if_exists("fixture_team_stats", "yellow_cards")
    drop_column_if_exists("fixture_team_stats", "ball_possession_pct")
    drop_column_if_exists("fixture_team_stats", "offsides")
    drop_column_if_exists("fixture_team_stats", "corner_kicks")
    drop_column_if_exists("fixture_team_stats", "fouls")
    drop_column_if_exists("fixture_team_stats", "shots_outside_box")
    drop_column_if_exists("fixture_team_stats", "shots_inside_box")
    drop_column_if_exists("fixture_team_stats", "blocked_shots")
    drop_column_if_exists("fixture_team_stats", "total_shots")
    drop_column_if_exists("fixture_team_stats", "shots_off_target")
    drop_column_if_exists("fixture_team_stats", "side")
