"""odds_bookmakers — discovery bookmakers API-Sports

Revision ID: 20260527120000
Revises: 20260526120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260527120000"
down_revision: Union[str, Sequence[str], None] = "20260526120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "odds_bookmakers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="api_sports"),
        sa.Column("provider_bookmaker_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
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
        sa.UniqueConstraint("provider", "provider_bookmaker_id", name="uq_odds_bookmakers_provider_id"),
    )
    op.create_index(op.f("ix_odds_bookmakers_provider"), "odds_bookmakers", ["provider"], unique=False)
    op.create_index(op.f("ix_odds_bookmakers_name"), "odds_bookmakers", ["name"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(op.f("ix_odds_bookmakers_name"), table_name="odds_bookmakers")
    op.drop_index(op.f("ix_odds_bookmakers_provider"), table_name="odds_bookmakers")
    op.drop_table("odds_bookmakers")
