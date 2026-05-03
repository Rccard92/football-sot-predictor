"""bootstrap league season team fixture columns

Revision ID: 20260505120000
Revises: 20260504100000
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260505120000"
down_revision: Union[str, Sequence[str], None] = "20260504100000"
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
    add_column_if_missing("leagues", sa.Column("logo_url", sa.String(length=512), nullable=True))
    add_column_if_missing("seasons", sa.Column("label", sa.String(length=32), nullable=True))
    add_column_if_missing(
        "seasons",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    add_column_if_missing("teams", sa.Column("code", sa.String(length=16), nullable=True))
    add_column_if_missing("teams", sa.Column("country", sa.String(length=128), nullable=True))
    add_column_if_missing("teams", sa.Column("founded", sa.Integer(), nullable=True))
    add_column_if_missing(
        "teams",
        sa.Column("national", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    add_column_if_missing("teams", sa.Column("venue_name", sa.String(length=255), nullable=True))
    add_column_if_missing("teams", sa.Column("venue_city", sa.String(length=128), nullable=True))
    add_column_if_missing("fixtures", sa.Column("round", sa.String(length=64), nullable=True))
    add_column_if_missing("fixtures", sa.Column("referee", sa.String(length=255), nullable=True))
    add_column_if_missing("fixtures", sa.Column("timezone", sa.String(length=64), nullable=True))
    add_column_if_missing("fixtures", sa.Column("status_long", sa.String(length=128), nullable=True))
    add_column_if_missing("fixtures", sa.Column("elapsed", sa.Integer(), nullable=True))
    add_column_if_missing("fixtures", sa.Column("venue_name", sa.String(length=255), nullable=True))
    add_column_if_missing("fixtures", sa.Column("venue_city", sa.String(length=128), nullable=True))


def downgrade() -> None:
    drop_column_if_exists("fixtures", "venue_city")
    drop_column_if_exists("fixtures", "venue_name")
    drop_column_if_exists("fixtures", "elapsed")
    drop_column_if_exists("fixtures", "status_long")
    drop_column_if_exists("fixtures", "timezone")
    drop_column_if_exists("fixtures", "referee")
    drop_column_if_exists("fixtures", "round")
    drop_column_if_exists("teams", "venue_city")
    drop_column_if_exists("teams", "venue_name")
    drop_column_if_exists("teams", "national")
    drop_column_if_exists("teams", "founded")
    drop_column_if_exists("teams", "country")
    drop_column_if_exists("teams", "code")
    drop_column_if_exists("seasons", "is_current")
    drop_column_if_exists("seasons", "label")
    drop_column_if_exists("leagues", "logo_url")
