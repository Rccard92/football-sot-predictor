"""backtest_round_analyses

Revision ID: 20260606120000
Revises: 20260605120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260606120000"
down_revision: Union[str, Sequence[str], None] = "20260605120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "backtest_round_analyses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("competition_id", sa.BigInteger(), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("analysis_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="historical_official_xi"),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("total_fixtures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_fixtures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_fixtures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("data_quality_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "competition_id",
            "season_year",
            "round_number",
            "analysis_version",
            name="uq_backtest_round_analyses_comp_season_round_ver",
        ),
    )
    op.create_index(
        "ix_backtest_round_analyses_competition_season",
        "backtest_round_analyses",
        ["competition_id", "season_year"],
        unique=False,
    )

    op.create_table(
        "backtest_round_fixture_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=True),
        sa.Column("home_team_name", sa.String(length=255), nullable=False),
        sa.Column("away_team_name", sa.String(length=255), nullable=False),
        sa.Column("actual_home_sot", sa.Integer(), nullable=True),
        sa.Column("actual_away_sot", sa.Integer(), nullable=True),
        sa.Column("actual_total_sot", sa.Integer(), nullable=True),
        sa.Column(
            "models_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("explanation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["backtest_round_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            "fixture_id",
            name="uq_backtest_round_fixture_results_analysis_fixture",
        ),
    )
    op.create_index(
        "ix_backtest_round_fixture_results_analysis_id",
        "backtest_round_fixture_results",
        ["analysis_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("backtest_round_fixture_results")
    op.drop_table("backtest_round_analyses")
