"""sportapi_odds_providers + sportapi_fixture_odds_snapshots

Revision ID: 20260529120000
Revises: 20260528120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260529120000"
down_revision: Union[str, Sequence[str], None] = "20260528120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "sportapi_odds_providers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_slug", sa.String(length=128), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False),
        sa.Column("provider_country", sa.String(length=8), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("odds_from_id", sa.Integer(), nullable=True),
        sa.Column("odds_from_slug", sa.String(length=128), nullable=True),
        sa.Column("odds_from_name", sa.String(length=255), nullable=True),
        sa.Column("live_odds_from_id", sa.Integer(), nullable=True),
        sa.Column("live_odds_from_slug", sa.String(length=128), nullable=True),
        sa.Column("live_odds_from_name", sa.String(length=255), nullable=True),
        sa.Column("default_bet_slip_link", sa.String(length=512), nullable=True),
        sa.Column("primary_color", sa.String(length=32), nullable=True),
        sa.Column("working_odds_provider_id", sa.Integer(), nullable=True),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_slug", name="uq_sportapi_odds_providers_slug"),
    )
    op.create_index(
        op.f("ix_sportapi_odds_providers_provider_slug"),
        "sportapi_odds_providers",
        ["provider_slug"],
        unique=True,
    )

    op.create_table(
        "sportapi_fixture_odds_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("api_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("sportapi_event_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_slug", sa.String(length=128), nullable=False),
        sa.Column("provider_id_used", sa.Integer(), nullable=True),
        sa.Column("market_key", sa.String(length=32), nullable=False, server_default="1x2"),
        sa.Column("market_name_original", sa.String(length=255), nullable=True),
        sa.Column("home_odd", sa.Float(), nullable=True),
        sa.Column("draw_odd", sa.Float(), nullable=True),
        sa.Column("away_odd", sa.Float(), nullable=True),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sportapi_fixture_odds_snap_fixture_provider",
        "sportapi_fixture_odds_snapshots",
        ["fixture_id", "provider_slug", "fetched_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("ix_sportapi_fixture_odds_snap_fixture_provider", table_name="sportapi_fixture_odds_snapshots")
    op.drop_table("sportapi_fixture_odds_snapshots")
    op.drop_index(op.f("ix_sportapi_odds_providers_provider_slug"), table_name="sportapi_odds_providers")
    op.drop_table("sportapi_odds_providers")
