"""bookmaker_markets + fixture_bookmaker_odds

Revision ID: 20260611120000
Revises: 20260610120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260611120000"
down_revision: Union[str, Sequence[str], None] = "20260610120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "bookmaker_markets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_source", sa.String(length=32), nullable=False),
        sa.Column("provider_market_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("market_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("market_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_market", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_source",
            "provider_market_id",
            name="uq_bookmaker_markets_provider_market",
        ),
    )
    op.create_index("ix_bookmaker_markets_provider_source", "bookmaker_markets", ["provider_source"])
    op.create_index("ix_bookmaker_markets_normalized_market", "bookmaker_markets", ["normalized_market"])

    op.create_table(
        "fixture_bookmaker_odds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("competition_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_source", sa.String(length=32), nullable=False),
        sa.Column("provider_bookmaker_id", sa.String(length=64), nullable=False),
        sa.Column("bookmaker_name", sa.String(length=255), nullable=False),
        sa.Column("provider_market_id", sa.String(length=128), nullable=True),
        sa.Column("normalized_market", sa.String(length=64), nullable=False),
        sa.Column("home_odds", sa.Float(), nullable=True),
        sa.Column("draw_odds", sa.Float(), nullable=True),
        sa.Column("away_odds", sa.Float(), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("odds_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "competition_id",
            "fixture_id",
            "provider_source",
            "provider_bookmaker_id",
            "normalized_market",
            name="uq_fixture_bookmaker_odds_scope",
        ),
    )
    op.create_index(
        "ix_fixture_bookmaker_odds_competition_fixture",
        "fixture_bookmaker_odds",
        ["competition_id", "fixture_id"],
    )
    op.create_index(
        "ix_fixture_bookmaker_odds_normalized_market",
        "fixture_bookmaker_odds",
        ["normalized_market"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("fixture_bookmaker_odds")
    op.drop_table("bookmaker_markets")
