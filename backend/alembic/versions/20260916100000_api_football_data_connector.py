"""collegamento dati API-Football: copertura campionati, partite scaricate, linee Bet365

Revision ID: 20260916100000_api_football_data
Revises: 20260916090000_live_predictions
Create Date: 2026-09-16 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260916100000_api_football_data"
down_revision: Union[str, Sequence[str], None] = "20260916090000_live_predictions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "api_football_league_coverage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("league_name", sa.String(255), nullable=True),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("league_type", sa.String(32), nullable=True),
        sa.Column("statistics_fixtures", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("lineups", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("events", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("odds", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("injuries", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider_league_id", "season", name="uq_api_football_league_coverage"),
    )
    op.create_index("ix_api_football_league_coverage_provider_league_id", "api_football_league_coverage", ["provider_league_id"])
    op.create_table(
        "api_football_fixture_fetches",
        sa.Column("api_fixture_id", sa.BigInteger(), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fixture_status", sa.String(16), nullable=True),
        sa.Column("stats_teams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stat_types", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lineups_teams", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_table(
        "cecchino_bet365_market_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_league_id", sa.BigInteger(), nullable=True),
        sa.Column("league_name", sa.String(255), nullable=True),
        sa.Column("market_key", sa.String(48), nullable=False),
        sa.Column("market_name", sa.String(96), nullable=False),
        sa.Column("line", sa.Numeric(5, 1), nullable=False),
        sa.Column("over_odd", sa.Numeric(8, 3), nullable=True),
        sa.Column("under_odd", sa.Numeric(8, 3), nullable=True),
        sa.Column("odds_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider_fixture_id", "market_key", "line", name="uq_cecchino_bet365_market_lines"),
    )
    op.create_index("ix_cecchino_bet365_market_lines_provider_fixture_id", "cecchino_bet365_market_lines", ["provider_fixture_id"])
    op.create_index("ix_cecchino_bet365_market_lines_scan_date_market", "cecchino_bet365_market_lines", ["scan_date", "market_key"])


def downgrade() -> None:
    op.drop_table("cecchino_bet365_market_lines")
    op.drop_table("api_football_fixture_fetches")
    op.drop_table("api_football_league_coverage")
