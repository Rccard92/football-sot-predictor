"""create_competitions

Revision ID: 20260604120000
Revises: 20260603120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260604120000"
down_revision: Union[str, Sequence[str], None] = "20260603120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "competitions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="api_sports"),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pre_match_cron_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("league_id", sa.BigInteger(), nullable=True),
        sa.Column("season_id", sa.BigInteger(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_competitions_key"),
    )
    op.create_index("ix_competitions_key", "competitions", ["key"])
    op.create_index("ix_competitions_provider_league_id", "competitions", ["provider_league_id"])
    op.create_index("ix_competitions_season", "competitions", ["season"])
    op.create_index("ix_competitions_is_active", "competitions", ["is_active"])
    op.create_index("ix_competitions_is_primary", "competitions", ["is_primary"])
    op.create_index(
        "ix_competitions_provider_league_season",
        "competitions",
        ["provider_league_id", "season"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_competitions_provider_league_season", table_name="competitions")
    op.drop_index("ix_competitions_is_primary", table_name="competitions")
    op.drop_index("ix_competitions_is_active", table_name="competitions")
    op.drop_index("ix_competitions_season", table_name="competitions")
    op.drop_index("ix_competitions_provider_league_id", table_name="competitions")
    op.drop_index("ix_competitions_key", table_name="competitions")
    op.drop_table("competitions")
