"""Migrazione cecchino_today_fixtures

Revision ID: 20260613120000
Revises: 20260612120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260613120000"
down_revision: Union[str, Sequence[str], None] = "20260612120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_today_fixtures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("provider_source", sa.String(length=32), nullable=False, server_default="api_football"),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("local_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("competition_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_season", sa.Integer(), nullable=True),
        sa.Column("country_name", sa.String(length=128), nullable=True),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("home_team_name", sa.String(length=255), nullable=True),
        sa.Column("away_team_name", sa.String(length=255), nullable=True),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fixture_status", sa.String(length=32), nullable=True),
        sa.Column("eligibility_status", sa.String(length=64), nullable=False, index=True),
        sa.Column("eligibility_reason", sa.String(length=512), nullable=True),
        sa.Column("bookmaker_status", sa.String(length=32), nullable=True),
        sa.Column("stats_status", sa.String(length=32), nullable=True),
        sa.Column("cecchino_status", sa.String(length=32), nullable=True),
        sa.Column("odds_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stats_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cecchino_output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("kpi_panel_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_fixture_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scan_date",
            "provider_source",
            "provider_fixture_id",
            name="uq_cecchino_today_scan_provider_fixture",
        ),
    )
    op.create_index("ix_cecchino_today_scan_date", "cecchino_today_fixtures", ["scan_date"])
    op.create_index(
        "ix_cecchino_today_eligibility",
        "cecchino_today_fixtures",
        ["scan_date", "eligibility_status"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("cecchino_today_fixtures")
