"""prediction_backtests squared_error and details

Revision ID: 20260504100000
Revises: 20260503120000
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260504100000"
down_revision: Union[str, Sequence[str], None] = "20260503120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def drop_column_if_exists(table_name: str, column_name: str) -> None:
    if column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    add_column_if_missing(
        "prediction_backtests",
        sa.Column(
            "squared_error",
            sa.Double(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    if column_exists("prediction_backtests", "squared_error"):
        op.alter_column("prediction_backtests", "squared_error", server_default=None)


def downgrade() -> None:
    drop_column_if_exists("prediction_backtests", "details")
    drop_column_if_exists("prediction_backtests", "squared_error")
