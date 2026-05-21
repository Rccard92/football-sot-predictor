"""fixture_lineup_refresh_impacts — snapshot pre/post refresh SportAPI

Revision ID: 20260525120000
Revises: 20260524120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260525120000"
down_revision: Union[str, Sequence[str], None] = "20260524120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "fixture_lineup_refresh_impacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False, server_default="sportapi"),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("before_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delta_home_sot", sa.Float(), nullable=True),
        sa.Column("delta_away_sot", sa.Float(), nullable=True),
        sa.Column("delta_total_sot", sa.Float(), nullable=True),
        sa.Column("direction_home", sa.String(length=8), nullable=True),
        sa.Column("direction_away", sa.String(length=8), nullable=True),
        sa.Column("direction_total", sa.String(length=8), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("main_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fixture_lineup_refresh_impacts_fixture_created",
        "fixture_lineup_refresh_impacts",
        ["fixture_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fixture_lineup_refresh_impacts_fixture_id"),
        "fixture_lineup_refresh_impacts",
        ["fixture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fixture_lineup_refresh_impacts_model_id"),
        "fixture_lineup_refresh_impacts",
        ["model_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(op.f("ix_fixture_lineup_refresh_impacts_model_id"), table_name="fixture_lineup_refresh_impacts")
    op.drop_index(op.f("ix_fixture_lineup_refresh_impacts_fixture_id"), table_name="fixture_lineup_refresh_impacts")
    op.drop_index("ix_fixture_lineup_refresh_impacts_fixture_created", table_name="fixture_lineup_refresh_impacts")
    op.drop_table("fixture_lineup_refresh_impacts")
