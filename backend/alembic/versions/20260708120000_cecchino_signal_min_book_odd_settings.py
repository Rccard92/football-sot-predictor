"""cecchino_signal_min_book_odd_settings table

Revision ID: 20260708120000
Revises: dd07defcb335
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260708120000"
down_revision: Union[str, Sequence[str], None] = "dd07defcb335"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_signal_min_book_odd_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_market_key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("min_book_odd", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("target_market_key"),
    )
    op.create_index(
        "ix_cecchino_signal_min_book_odd_settings_target_market_key",
        "cecchino_signal_min_book_odd_settings",
        ["target_market_key"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_cecchino_signal_min_book_odd_settings_target_market_key",
        table_name="cecchino_signal_min_book_odd_settings",
    )
    op.drop_table("cecchino_signal_min_book_odd_settings")
