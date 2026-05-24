"""tracked_betting_picks: snapshot previsione iniziale e quote nullable

Revision ID: 20260601120000
Revises: 20260531120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260601120000"
down_revision: Union[str, Sequence[str], None] = "20260531120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for col in (
        "initial_predicted_home_sot",
        "initial_predicted_away_sot",
        "initial_predicted_total_sot",
        "initial_line_value",
        "initial_odd",
        "official_odd",
    ):
        op.add_column("tracked_betting_picks", sa.Column(col, sa.Float(), nullable=True))
    op.add_column(
        "tracked_betting_picks",
        sa.Column("initial_suggested_pick", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_column("tracked_betting_picks", "initial_suggested_pick")
    for col in (
        "official_odd",
        "initial_odd",
        "initial_line_value",
        "initial_predicted_total_sot",
        "initial_predicted_away_sot",
        "initial_predicted_home_sot",
    ):
        op.drop_column("tracked_betting_picks", col)
