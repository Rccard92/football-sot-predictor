"""tracked_betting_picks: backfill fields + unique backfill/manual

Revision ID: 20260530120000
Revises: 20260529120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260530120000"
down_revision: Union[str, Sequence[str], None] = "20260529120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "tracked_betting_picks",
        sa.Column("is_backfilled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "tracked_betting_picks",
        sa.Column("prediction_source", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tracked_betting_picks",
        sa.Column("backfill_warning", sa.Text(), nullable=True),
    )
    op.create_index(
        "uq_tracked_betting_picks_backfill_manual",
        "tracked_betting_picks",
        ["fixture_id", "model_id", "market_id", "pick_type"],
        unique=True,
        postgresql_where=sa.text("source IN ('backfill_round', 'manual')"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_tracked_betting_picks_backfill_manual", table_name="tracked_betting_picks")
    op.drop_column("tracked_betting_picks", "backfill_warning")
    op.drop_column("tracked_betting_picks", "prediction_source")
    op.drop_column("tracked_betting_picks", "is_backfilled")
