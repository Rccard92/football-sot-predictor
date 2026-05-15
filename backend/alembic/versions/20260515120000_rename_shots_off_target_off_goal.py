"""Rename fixture_team_stats.shots_off_target to shots_off_goal (API-Football Shots off Goal)

Revision ID: 20260515120000
Revises: 20260514120000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260515120000"
down_revision: Union[str, Sequence[str], None] = "20260514120000"
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


def upgrade() -> None:
    if not table_exists("fixture_team_stats"):
        return
    if column_exists("fixture_team_stats", "shots_off_goal"):
        return
    if not column_exists("fixture_team_stats", "shots_off_target"):
        return
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text('ALTER TABLE fixture_team_stats RENAME COLUMN shots_off_target TO shots_off_goal'),
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text("ALTER TABLE fixture_team_stats RENAME COLUMN shots_off_target TO shots_off_goal"),
        )
    elif dialect == "mysql":
        op.execute(
            sa.text(
                "ALTER TABLE fixture_team_stats CHANGE shots_off_target shots_off_goal INTEGER NULL",
            ),
        )
    else:
        op.execute(
            sa.text('ALTER TABLE fixture_team_stats RENAME COLUMN shots_off_target TO shots_off_goal'),
        )


def downgrade() -> None:
    if not table_exists("fixture_team_stats"):
        return
    if column_exists("fixture_team_stats", "shots_off_target"):
        return
    if not column_exists("fixture_team_stats", "shots_off_goal"):
        return
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text('ALTER TABLE fixture_team_stats RENAME COLUMN shots_off_goal TO shots_off_target'),
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text("ALTER TABLE fixture_team_stats RENAME COLUMN shots_off_goal TO shots_off_target"),
        )
    elif dialect == "mysql":
        op.execute(
            sa.text(
                "ALTER TABLE fixture_team_stats CHANGE shots_off_goal shots_off_target INTEGER NULL",
            ),
        )
    else:
        op.execute(
            sa.text('ALTER TABLE fixture_team_stats RENAME COLUMN shots_off_goal TO shots_off_target'),
        )
