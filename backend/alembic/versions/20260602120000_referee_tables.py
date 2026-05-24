"""referees, fixture_referees, referee_season_profiles

Revision ID: 20260602120000
Revises: 20260601120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260602120000"
down_revision: Union[str, Sequence[str], None] = "20260601120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "referees",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="api_sports"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "normalized_name", name="uq_referees_provider_normalized_name"),
    )
    op.create_index(op.f("ix_referees_normalized_name"), "referees", ["normalized_name"], unique=False)

    op.create_table(
        "fixture_referees",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("api_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("referee_id", sa.BigInteger(), nullable=True),
        sa.Column("referee_name", sa.String(length=255), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="api_sports"),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referee_id"], ["referees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fixture_id", "source", name="uq_fixture_referees_fixture_source"),
    )
    op.create_index(op.f("ix_fixture_referees_fixture_id"), "fixture_referees", ["fixture_id"], unique=False)
    op.create_index(op.f("ix_fixture_referees_api_fixture_id"), "fixture_referees", ["api_fixture_id"], unique=False)
    op.create_index(op.f("ix_fixture_referees_referee_id"), "fixture_referees", ["referee_id"], unique=False)

    op.create_table(
        "referee_season_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("referee_id", sa.BigInteger(), nullable=False),
        sa.Column("league_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("matches_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_yellow_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_red_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_yellow_cards", sa.Float(), nullable=True),
        sa.Column("avg_red_cards", sa.Float(), nullable=True),
        sa.Column("severity_label", sa.String(length=64), nullable=True),
        sa.Column("sample_quality", sa.String(length=16), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["referee_id"], ["referees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "referee_id",
            "league_id",
            "season",
            name="uq_referee_season_profiles_referee_league_season",
        ),
    )
    op.create_index(
        op.f("ix_referee_season_profiles_referee_id"),
        "referee_season_profiles",
        ["referee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_season_profiles_league_id"),
        "referee_season_profiles",
        ["league_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_referee_season_profiles_season"),
        "referee_season_profiles",
        ["season"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("referee_season_profiles")
    op.drop_table("fixture_referees")
    op.drop_table("referees")
