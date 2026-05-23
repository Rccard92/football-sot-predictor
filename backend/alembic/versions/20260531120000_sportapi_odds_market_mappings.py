"""sportapi_odds_market_mappings

Revision ID: 20260531120000
Revises: 20260530120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260531120000"
down_revision: Union[str, Sequence[str], None] = "20260530120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "sportapi_odds_market_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_slug", sa.String(length=128), nullable=False),
        sa.Column("provider_id_used", sa.Integer(), nullable=True),
        sa.Column("raw_market_name", sa.String(length=255), nullable=False),
        sa.Column("raw_market_id", sa.String(length=128), nullable=True),
        sa.Column("normalized_market_key", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sample_raw_market", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.UniqueConstraint(
            "provider_slug",
            "raw_market_name",
            "normalized_market_key",
            name="uq_sportapi_odds_market_mappings_slug_name_key",
        ),
    )
    op.create_index(
        op.f("ix_sportapi_odds_market_mappings_provider_slug"),
        "sportapi_odds_market_mappings",
        ["provider_slug"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(
        op.f("ix_sportapi_odds_market_mappings_provider_slug"),
        table_name="sportapi_odds_market_mappings",
    )
    op.drop_table("sportapi_odds_market_mappings")
