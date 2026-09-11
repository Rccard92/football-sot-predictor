"""cecchino pattern discovery tables (walk-forward Pattern/Formula engine)

Revision ID: 20260912100000_patdisc
Revises: 20260910140000_run_v2_ips
Create Date: 2026-09-12 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260912100000_patdisc"
down_revision: Union[str, Sequence[str], None] = "20260910140000_run_v2_ips"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_pattern_discovery_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("run_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("folds_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("folds_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_git_commit", sa.String(length=64), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_pattern_discovery_runs_market_key",
        "cecchino_pattern_discovery_runs",
        ["market_key"],
    )
    op.create_index(
        "ix_cecchino_pattern_discovery_runs_status",
        "cecchino_pattern_discovery_runs",
        ["status"],
    )
    op.create_index(
        "ix_cecchino_pattern_disc_runs_market_status",
        "cecchino_pattern_discovery_runs",
        ["market_key", "status"],
    )

    op.create_table(
        "cecchino_discovered_patterns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("discovery_run_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("fold_index", sa.Integer(), nullable=False),
        sa.Column("train_seasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_season", sa.String(length=32), nullable=False),
        sa.Column("formula_slot", sa.String(length=1), nullable=True),
        sa.Column("rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("train_n", sa.Integer(), nullable=False),
        sa.Column("train_wins", sa.Integer(), nullable=False),
        sa.Column("train_win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("train_avg_profit_1u", sa.Numeric(10, 4), nullable=True),
        sa.Column("oos_n", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("oos_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("oos_win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("oos_win_rate_ci_low_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("oos_win_rate_ci_high_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("oos_avg_profit_1u", sa.Numeric(10, 4), nullable=True),
        sa.Column("oos_avg_profit_ci_low", sa.Numeric(10, 4), nullable=True),
        sa.Column("oos_avg_profit_ci_high", sa.Numeric(10, 4), nullable=True),
        sa.Column("oos_avg_quota_book", sa.Numeric(10, 3), nullable=True),
        sa.Column("breakeven_win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("promoted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("promotion_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"],
            ["cecchino_pattern_discovery_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_discovered_patterns_market_key",
        "cecchino_discovered_patterns",
        ["market_key"],
    )
    op.create_index(
        "ix_cecchino_discovered_patterns_run_fold",
        "cecchino_discovered_patterns",
        ["discovery_run_id", "fold_index"],
    )
    op.create_index(
        "ix_cecchino_discovered_patterns_market_promoted",
        "cecchino_discovered_patterns",
        ["market_key", "promoted"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_discovered_patterns_market_promoted",
        table_name="cecchino_discovered_patterns",
    )
    op.drop_index(
        "ix_cecchino_discovered_patterns_run_fold",
        table_name="cecchino_discovered_patterns",
    )
    op.drop_index(
        "ix_cecchino_discovered_patterns_market_key",
        table_name="cecchino_discovered_patterns",
    )
    op.drop_table("cecchino_discovered_patterns")

    op.drop_index(
        "ix_cecchino_pattern_disc_runs_market_status",
        table_name="cecchino_pattern_discovery_runs",
    )
    op.drop_index(
        "ix_cecchino_pattern_discovery_runs_status",
        table_name="cecchino_pattern_discovery_runs",
    )
    op.drop_index(
        "ix_cecchino_pattern_discovery_runs_market_key",
        table_name="cecchino_pattern_discovery_runs",
    )
    op.drop_table("cecchino_pattern_discovery_runs")
