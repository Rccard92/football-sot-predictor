"""player_provider_mappings — SportAPI player id ↔ API-Football player id

Revision ID: 20260524120000
Revises: 20260523120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260524120000"
down_revision: Union[str, Sequence[str], None] = "20260523120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "player_provider_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("api_sports_player_id", sa.BigInteger(), nullable=True),
        sa.Column("sportapi_player_id", sa.BigInteger(), nullable=False),
        sa.Column("player_name_api_sports", sa.String(length=255), nullable=True),
        sa.Column("player_name_sportapi", sa.String(length=255), nullable=False),
        sa.Column("api_sports_team_id", sa.BigInteger(), nullable=True),
        sa.Column("sportapi_team_id", sa.BigInteger(), nullable=True),
        sa.Column("league_id", sa.BigInteger(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("matched_by", sa.String(length=64), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sportapi_player_id",
            "api_sports_team_id",
            "season",
            name="uq_player_provider_mappings_sportapi_team_season",
        ),
    )
    op.create_index(
        "ix_player_provider_mappings_api_sports_player_id",
        "player_provider_mappings",
        ["api_sports_player_id"],
    )
    op.create_index(
        "ix_player_provider_mappings_sportapi_player_id",
        "player_provider_mappings",
        ["sportapi_player_id"],
    )
    op.create_index(
        "ix_player_provider_mappings_league_id",
        "player_provider_mappings",
        ["league_id"],
    )
    op.create_index(
        "ix_player_provider_mappings_season",
        "player_provider_mappings",
        ["season"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("player_provider_mappings")
