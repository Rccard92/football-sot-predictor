"""player_availability: unique index includes source_detail

Revision ID: 20260522120000
Revises: 20260521120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260522120000"
down_revision: Union[str, Sequence[str], None] = "20260521120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_player_availability_with_fixture", table_name="player_availability")
    op.create_index(
        "uq_player_availability_with_fixture",
        "player_availability",
        ["season", "league_id", "api_fixture_id", "api_team_id", "api_player_id", "source", "source_detail"],
        unique=True,
        postgresql_where=sa.text("api_fixture_id IS NOT NULL AND source_detail IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_player_availability_with_fixture", table_name="player_availability")
    op.create_index(
        "uq_player_availability_with_fixture",
        "player_availability",
        ["season", "league_id", "api_fixture_id", "api_team_id", "api_player_id", "source"],
        unique=True,
        postgresql_where=sa.text("api_fixture_id IS NOT NULL"),
    )
