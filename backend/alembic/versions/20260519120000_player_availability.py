"""player_availability table (stage 8A)

Revision ID: 20260519120000
Revises: 20260518120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260519120000"
down_revision: Union[str, Sequence[str], None] = "20260518120000"
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
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if not table_exists("player_availability"):
        op.create_table(
            "player_availability",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("league_id", sa.BigInteger(), nullable=False),
            sa.Column("fixture_id", sa.BigInteger(), nullable=True),
            sa.Column("api_fixture_id", sa.BigInteger(), nullable=True),
            sa.Column("team_id", sa.BigInteger(), nullable=True),
            sa.Column("api_team_id", sa.BigInteger(), nullable=True),
            sa.Column("team_name", sa.Text(), nullable=True),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("api_player_id", sa.BigInteger(), nullable=True),
            sa.Column("player_name", sa.String(length=255), nullable=False),
            sa.Column("availability_status", sa.String(length=32), nullable=False),
            sa.Column("availability_type", sa.String(length=32), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "fetched_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["player_id"], ["player_registry.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_player_availability_season_league", "player_availability", ["season", "league_id"])
        op.create_index("ix_player_availability_fixture_id", "player_availability", ["fixture_id"])
        op.create_index("ix_player_availability_api_team_id", "player_availability", ["api_team_id"])
        op.create_index("ix_player_availability_api_player_id", "player_availability", ["api_player_id"])
        op.create_index("ix_player_availability_is_active", "player_availability", ["is_active"])

        op.create_index(
            "uq_player_availability_with_fixture",
            "player_availability",
            ["season", "league_id", "api_fixture_id", "api_team_id", "api_player_id", "source"],
            unique=True,
            postgresql_where=sa.text("api_fixture_id IS NOT NULL"),
        )
        op.create_index(
            "uq_player_availability_no_fixture",
            "player_availability",
            ["season", "league_id", "api_team_id", "api_player_id", "source", "reason"],
            unique=True,
            postgresql_where=sa.text("api_fixture_id IS NULL"),
        )


def downgrade() -> None:
    if table_exists("player_availability"):
        op.drop_table("player_availability")
