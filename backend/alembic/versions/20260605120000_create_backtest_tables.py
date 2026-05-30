"""create_backtest_tables

Revision ID: 20260605120000
Revises: 20260604130000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260605120000"
down_revision: Union[str, Sequence[str], None] = "20260604130000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("competition_id", sa.BigInteger(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=True),
        sa.Column("season_year", sa.Integer(), nullable=True),
        sa.Column("market_key", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("fixture_scope", sa.String(length=32), nullable=False),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("algorithm_config_hash", sa.String(length=64), nullable=False),
        sa.Column("model_manifest_version", sa.String(length=64), nullable=True),
        sa.Column("git_commit_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_runs_competition_market_algorithm",
        "backtest_runs",
        ["competition_id", "market_key", "algorithm_version"],
        unique=False,
    )
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"], unique=False)
    op.create_index("ix_backtest_runs_created_at", "backtest_runs", ["created_at"], unique=False)
    op.create_index(
        "ix_backtest_runs_competition_season",
        "backtest_runs",
        ["competition_id", "season_year"],
        unique=False,
    )

    op.create_table(
        "backtest_predictions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("backtest_run_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("prediction_scope", sa.String(length=32), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("error_value", sa.Float(), nullable=True),
        sa.Column("abs_error", sa.Float(), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feature_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"],
            ["backtest_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "backtest_run_id",
            "fixture_id",
            "prediction_scope",
            name="uq_backtest_predictions_run_fixture_scope",
        ),
    )
    op.create_index(
        "ix_backtest_predictions_run",
        "backtest_predictions",
        ["backtest_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_predictions_fixture",
        "backtest_predictions",
        ["fixture_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_predictions_competition_market_algorithm",
        "backtest_predictions",
        ["competition_id", "market_key", "algorithm_version"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_predictions_scope",
        "backtest_predictions",
        ["prediction_scope"],
        unique=False,
    )

    op.create_table(
        "backtest_picks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("backtest_run_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("prediction_scope", sa.String(length=32), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("bet_type", sa.String(length=32), nullable=False),
        sa.Column("line_value", sa.Float(), nullable=False),
        sa.Column("pick_side", sa.String(length=16), nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=True),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("confidence_label", sa.String(length=64), nullable=True),
        sa.Column("risk_label", sa.String(length=64), nullable=True),
        sa.Column("odds", sa.Float(), nullable=True),
        sa.Column("profit_loss", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"],
            ["backtest_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "backtest_run_id",
            "fixture_id",
            "prediction_scope",
            "bet_type",
            "line_value",
            "pick_side",
            name="uq_backtest_picks_run_fixture_scope_bet",
        ),
    )
    op.create_index("ix_backtest_picks_run", "backtest_picks", ["backtest_run_id"], unique=False)
    op.create_index("ix_backtest_picks_fixture", "backtest_picks", ["fixture_id"], unique=False)
    op.create_index(
        "ix_backtest_picks_market_algorithm",
        "backtest_picks",
        ["market_key", "algorithm_version"],
        unique=False,
    )
    op.create_index("ix_backtest_picks_result", "backtest_picks", ["result"], unique=False)
    op.create_index("ix_backtest_picks_line", "backtest_picks", ["line_value"], unique=False)

    op.create_table(
        "backtest_run_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("backtest_run_id", sa.BigInteger(), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("metric_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"],
            ["backtest_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "backtest_run_id",
            "metric_key",
            name="uq_backtest_run_metrics_run_key",
        ),
    )
    op.create_index(
        "ix_backtest_run_metrics_run",
        "backtest_run_metrics",
        ["backtest_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_run_metrics_key",
        "backtest_run_metrics",
        ["metric_key"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_backtest_run_metrics_key", table_name="backtest_run_metrics")
    op.drop_index("ix_backtest_run_metrics_run", table_name="backtest_run_metrics")
    op.drop_table("backtest_run_metrics")

    op.drop_index("ix_backtest_picks_line", table_name="backtest_picks")
    op.drop_index("ix_backtest_picks_result", table_name="backtest_picks")
    op.drop_index("ix_backtest_picks_market_algorithm", table_name="backtest_picks")
    op.drop_index("ix_backtest_picks_fixture", table_name="backtest_picks")
    op.drop_index("ix_backtest_picks_run", table_name="backtest_picks")
    op.drop_table("backtest_picks")

    op.drop_index("ix_backtest_predictions_scope", table_name="backtest_predictions")
    op.drop_index(
        "ix_backtest_predictions_competition_market_algorithm",
        table_name="backtest_predictions",
    )
    op.drop_index("ix_backtest_predictions_fixture", table_name="backtest_predictions")
    op.drop_index("ix_backtest_predictions_run", table_name="backtest_predictions")
    op.drop_table("backtest_predictions")

    op.drop_index("ix_backtest_runs_competition_season", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_created_at", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_status", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_competition_market_algorithm", table_name="backtest_runs")
    op.drop_table("backtest_runs")
