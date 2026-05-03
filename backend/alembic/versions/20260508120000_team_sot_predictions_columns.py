"""team_sot_predictions: colonne esplicite per baseline e quote future

Revision ID: 20260508120000
Revises: 20260507140000
Create Date: 2026-05-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508120000"
down_revision: Union[str, Sequence[str], None] = "20260507140000"
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
    add_column_if_missing("team_sot_predictions", sa.Column("actual_sot", sa.Integer(), nullable=True))
    add_column_if_missing(
        "team_sot_predictions",
        sa.Column("confidence_score", sa.Integer(), nullable=True),
    )
    add_column_if_missing("team_sot_predictions", sa.Column("explanation", sa.Text(), nullable=True))
    add_column_if_missing("team_sot_predictions", sa.Column("line_value", sa.Double(), nullable=True))
    add_column_if_missing(
        "team_sot_predictions",
        sa.Column("over_probability", sa.Double(), nullable=True),
    )
    add_column_if_missing(
        "team_sot_predictions",
        sa.Column("under_probability", sa.Double(), nullable=True),
    )
    add_column_if_missing(
        "team_sot_predictions",
        sa.Column("recommendation", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    drop_column_if_exists("team_sot_predictions", "recommendation")
    drop_column_if_exists("team_sot_predictions", "under_probability")
    drop_column_if_exists("team_sot_predictions", "over_probability")
    drop_column_if_exists("team_sot_predictions", "line_value")
    drop_column_if_exists("team_sot_predictions", "explanation")
    drop_column_if_exists("team_sot_predictions", "confidence_score")
    drop_column_if_exists("team_sot_predictions", "actual_sot")
