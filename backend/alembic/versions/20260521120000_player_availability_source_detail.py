"""player_availability: source_detail

Revision ID: 20260521120000
Revises: 20260520120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260521120000"
down_revision: Union[str, Sequence[str], None] = "20260520120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.add_column(
        "player_availability",
        sa.Column("source_detail", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_player_availability_source_detail",
        "player_availability",
        ["source_detail"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("ix_player_availability_source_detail", table_name="player_availability")
    op.drop_column("player_availability", "source_detail")
