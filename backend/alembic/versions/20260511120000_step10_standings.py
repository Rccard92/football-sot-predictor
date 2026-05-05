"""step10: standings snapshots and entries

Revision ID: 20260511120000
Revises: 20260510120000
Create Date: 2026-05-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260511120000"
down_revision: Union[str, Sequence[str], None] = "20260510120000"
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


def upgrade() -> None:
    if not table_exists("standings_snapshots"):
        op.create_table(
            "standings_snapshots",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("season_id", sa.BigInteger(), nullable=False),
            sa.Column("league_id", sa.BigInteger(), nullable=False),
            sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_standings_snapshots_season_id"),
            "standings_snapshots",
            ["season_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_standings_snapshots_league_id"),
            "standings_snapshots",
            ["league_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_standings_snapshots_snapshot_at"),
            "standings_snapshots",
            ["snapshot_at"],
            unique=False,
        )

    if not table_exists("standing_entries"):
        op.create_table(
            "standing_entries",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
            sa.Column("season_id", sa.BigInteger(), nullable=False),
            sa.Column("league_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.Column("points", sa.Integer(), nullable=True),
            sa.Column("goals_diff", sa.Integer(), nullable=True),
            sa.Column("played", sa.Integer(), nullable=True),
            sa.Column("win", sa.Integer(), nullable=True),
            sa.Column("draw", sa.Integer(), nullable=True),
            sa.Column("lose", sa.Integer(), nullable=True),
            sa.Column("goals_for", sa.Integer(), nullable=True),
            sa.Column("goals_against", sa.Integer(), nullable=True),
            sa.Column("form", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["snapshot_id"], ["standings_snapshots.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("snapshot_id", "team_id", name="uq_standing_entries_snapshot_team"),
        )
        op.create_index(op.f("ix_standing_entries_snapshot_id"), "standing_entries", ["snapshot_id"], unique=False)
        op.create_index(op.f("ix_standing_entries_season_id"), "standing_entries", ["season_id"], unique=False)
        op.create_index(op.f("ix_standing_entries_league_id"), "standing_entries", ["league_id"], unique=False)
        op.create_index(op.f("ix_standing_entries_team_id"), "standing_entries", ["team_id"], unique=False)
        op.create_index(op.f("ix_standing_entries_rank"), "standing_entries", ["rank"], unique=False)


def downgrade() -> None:
    if table_exists("standing_entries"):
        op.drop_index(op.f("ix_standing_entries_rank"), table_name="standing_entries")
        op.drop_index(op.f("ix_standing_entries_team_id"), table_name="standing_entries")
        op.drop_index(op.f("ix_standing_entries_league_id"), table_name="standing_entries")
        op.drop_index(op.f("ix_standing_entries_season_id"), table_name="standing_entries")
        op.drop_index(op.f("ix_standing_entries_snapshot_id"), table_name="standing_entries")
        op.drop_table("standing_entries")

    if table_exists("standings_snapshots"):
        op.drop_index(op.f("ix_standings_snapshots_snapshot_at"), table_name="standings_snapshots")
        op.drop_index(op.f("ix_standings_snapshots_league_id"), table_name="standings_snapshots")
        op.drop_index(op.f("ix_standings_snapshots_season_id"), table_name="standings_snapshots")
        op.drop_table("standings_snapshots")
