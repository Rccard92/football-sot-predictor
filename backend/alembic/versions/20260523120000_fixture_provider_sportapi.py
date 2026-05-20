"""fixture_provider_* tables for SportAPI debug storage

Revision ID: 20260523120000
Revises: 20260522120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260523120000"
down_revision: Union[str, Sequence[str], None] = "20260522120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "fixture_provider_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_unique_tournament_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_season_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_home_team_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_away_team_id", sa.BigInteger(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("matched_by", sa.String(length=64), nullable=True),
        sa.Column("match_date", sa.Date(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fixture_id", "provider_name", name="uq_fixture_provider_mappings_fixture_provider"),
    )
    op.create_index("ix_fixture_provider_mappings_fixture_id", "fixture_provider_mappings", ["fixture_id"])
    op.create_index("ix_fixture_provider_mappings_provider_event_id", "fixture_provider_mappings", ["provider_event_id"])

    op.create_table(
        "fixture_provider_lineups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.BigInteger(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("home_formation", sa.String(length=32), nullable=True),
        sa.Column("away_formation", sa.String(length=32), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fixture_id", "provider_name", name="uq_fixture_provider_lineups_fixture_provider"),
    )
    op.create_index("ix_fixture_provider_lineups_fixture_id", "fixture_provider_lineups", ["fixture_id"])
    op.create_index("ix_fixture_provider_lineups_provider_event_id", "fixture_provider_lineups", ["provider_event_id"])

    op.create_table(
        "fixture_provider_lineup_players",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_lineup_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("provider_player_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_team_id", sa.BigInteger(), nullable=True),
        sa.Column("team_side", sa.String(length=8), nullable=False),
        sa.Column("player_name", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=128), nullable=True),
        sa.Column("position", sa.String(length=32), nullable=True),
        sa.Column("jersey_number", sa.Integer(), nullable=True),
        sa.Column("is_substitute", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_lineup_id"], ["fixture_provider_lineups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fixture_id",
            "provider_name",
            "provider_player_id",
            "team_side",
            "is_substitute",
            name="uq_fixture_provider_lineup_players_natural",
        ),
    )
    op.create_index("ix_fixture_provider_lineup_players_fixture_id", "fixture_provider_lineup_players", ["fixture_id"])

    op.create_table(
        "fixture_missing_players",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_lineup_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("provider_player_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_team_id", sa.BigInteger(), nullable=True),
        sa.Column("team_side", sa.String(length=8), nullable=False),
        sa.Column("player_name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=32), nullable=True),
        sa.Column("jersey_number", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("external_type", sa.String(length=64), nullable=True),
        sa.Column("expected_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_lineup_id"], ["fixture_provider_lineups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fixture_id",
            "provider_name",
            "provider_player_id",
            "team_side",
            name="uq_fixture_missing_players_natural",
        ),
    )
    op.create_index("ix_fixture_missing_players_fixture_id", "fixture_missing_players", ["fixture_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("fixture_missing_players")
    op.drop_table("fixture_provider_lineup_players")
    op.drop_table("fixture_provider_lineups")
    op.drop_table("fixture_provider_mappings")
