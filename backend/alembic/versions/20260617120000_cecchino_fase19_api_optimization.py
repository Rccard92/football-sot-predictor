"""cecchino fase19 api optimization

Revision ID: 20260617120000
Revises: 20260616120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260617120000"
down_revision: Union[str, Sequence[str], None] = "20260616120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "api_usage_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_source", sa.String(length=32), nullable=False, server_default="api_football"),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=True),
        sa.Column("request_params_hash", sa.String(length=64), nullable=True),
        sa.Column("request_params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("negative_cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_usage_events_created_at", "api_usage_events", ["created_at"])
    op.create_index("ix_api_usage_events_scan_date", "api_usage_events", ["scan_date"])
    op.create_index("ix_api_usage_events_job_id", "api_usage_events", ["job_id"])

    op.add_column(
        "cecchino_today_fixtures",
        sa.Column("odds_check_status", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "cecchino_today_fixtures",
        sa.Column("odds_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cecchino_today_fixtures",
        sa.Column("negative_cache_until", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "cecchino_league_stats_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("last_stats_import_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fixtures_ft_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_minimum_stats", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stats_quality_status", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_league_id",
            "season",
            name="uq_cecchino_league_stats_cache_league_season",
        ),
    )
    op.create_index(
        "ix_cecchino_league_stats_cache_provider_league_id",
        "cecchino_league_stats_cache",
        ["provider_league_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_cecchino_league_stats_cache_provider_league_id", table_name="cecchino_league_stats_cache")
    op.drop_table("cecchino_league_stats_cache")
    op.drop_column("cecchino_today_fixtures", "negative_cache_until")
    op.drop_column("cecchino_today_fixtures", "odds_checked_at")
    op.drop_column("cecchino_today_fixtures", "odds_check_status")
    op.drop_index("ix_api_usage_events_job_id", table_name="api_usage_events")
    op.drop_index("ix_api_usage_events_scan_date", table_name="api_usage_events")
    op.drop_index("ix_api_usage_events_created_at", table_name="api_usage_events")
    op.drop_table("api_usage_events")
