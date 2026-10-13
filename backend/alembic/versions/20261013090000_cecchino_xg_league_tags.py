"""Cecchino Today: tag permanente dei campionati con o senza xG (solo additiva).

Revision ID: 20261013090000_xg_league_tags
Revises: 20260920090000_cecchino_v4
Create Date: 2026-10-13 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261013090000_xg_league_tags"
down_revision: Union[str, Sequence[str], None] = "20260920090000_cecchino_v4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_xg_league_tags",
        sa.Column("provider_league_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("fixtures_answered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fixtures_with_xg", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cecchino_xg_league_tags")
