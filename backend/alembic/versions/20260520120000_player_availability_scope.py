"""player_availability: record_scope + fixture_date

Revision ID: 20260520120000
Revises: 20260519120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260520120000"
down_revision: Union[str, Sequence[str], None] = "20260519120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "player_availability",
        sa.Column("record_scope", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "player_availability",
        sa.Column("fixture_date", sa.Date(), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE player_availability
            SET record_scope = CASE
                WHEN api_fixture_id IS NOT NULL THEN 'fixture_level'
                WHEN api_team_id IS NOT NULL THEN 'team_level'
                ELSE 'season_level'
            END
            WHERE record_scope IS NULL
            """
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE player_availability
            SET fixture_date = (reported_at AT TIME ZONE 'UTC')::date
            WHERE fixture_date IS NULL AND reported_at IS NOT NULL
            """
        ),
    )

    op.alter_column("player_availability", "record_scope", nullable=False)
    op.create_index(
        "ix_player_availability_record_scope",
        "player_availability",
        ["record_scope"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("ix_player_availability_record_scope", table_name="player_availability")
    op.drop_column("player_availability", "fixture_date")
    op.drop_column("player_availability", "record_scope")
