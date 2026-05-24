"""referee_fixture_card_summaries

Revision ID: 20260603120000
Revises: 20260602120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260603120000"
down_revision: Union[str, Sequence[str], None] = "20260602120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "referee_fixture_card_summaries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("api_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("referee_id", sa.BigInteger(), nullable=False),
        sa.Column("league_api_id", sa.BigInteger(), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("home_team_api_id", sa.BigInteger(), nullable=True),
        sa.Column("away_team_api_id", sa.BigInteger(), nullable=True),
        sa.Column("home_team_name", sa.String(length=255), nullable=True),
        sa.Column("away_team_name", sa.String(length=255), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_yellow", sa.Integer(), nullable=True),
        sa.Column("total_red", sa.Integer(), nullable=True),
        sa.Column("home_yellow", sa.Integer(), nullable=True),
        sa.Column("home_red", sa.Integer(), nullable=True),
        sa.Column("away_yellow", sa.Integer(), nullable=True),
        sa.Column("away_red", sa.Integer(), nullable=True),
        sa.Column("card_source", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referee_id"], ["referees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_fixture_id", name="uq_referee_fixture_card_summaries_api_fixture_id"),
    )
    op.create_index(
        op.f("ix_referee_fixture_card_summaries_api_fixture_id"),
        "referee_fixture_card_summaries",
        ["api_fixture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_fixture_card_summaries_fixture_id"),
        "referee_fixture_card_summaries",
        ["fixture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_fixture_card_summaries_referee_id"),
        "referee_fixture_card_summaries",
        ["referee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_fixture_card_summaries_league_api_id"),
        "referee_fixture_card_summaries",
        ["league_api_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_fixture_card_summaries_season_year"),
        "referee_fixture_card_summaries",
        ["season_year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_fixture_card_summaries_kickoff_at"),
        "referee_fixture_card_summaries",
        ["kickoff_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("referee_fixture_card_summaries")
