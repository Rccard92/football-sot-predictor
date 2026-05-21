"""odds_discovery_snapshots — audit discovery quote

Revision ID: 20260528120000
Revises: 20260527120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528120000"
down_revision: Union[str, Sequence[str], None] = "20260527120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "odds_discovery_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("api_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("sportapi_event_id", sa.BigInteger(), nullable=True),
        sa.Column("sportapi_provider_id", sa.Integer(), nullable=True),
        sa.Column("markets_count", sa.Integer(), nullable=True),
        sa.Column("bookmakers_count", sa.Integer(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_odds_discovery_snapshots_provider"),
        "odds_discovery_snapshots",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_odds_discovery_snapshots_fixture_id"),
        "odds_discovery_snapshots",
        ["fixture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_odds_discovery_snapshots_sportapi_event_id"),
        "odds_discovery_snapshots",
        ["sportapi_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_odds_discovery_snapshots_created_at"),
        "odds_discovery_snapshots",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(op.f("ix_odds_discovery_snapshots_created_at"), table_name="odds_discovery_snapshots")
    op.drop_index(op.f("ix_odds_discovery_snapshots_sportapi_event_id"), table_name="odds_discovery_snapshots")
    op.drop_index(op.f("ix_odds_discovery_snapshots_fixture_id"), table_name="odds_discovery_snapshots")
    op.drop_index(op.f("ix_odds_discovery_snapshots_provider"), table_name="odds_discovery_snapshots")
    op.drop_table("odds_discovery_snapshots")
