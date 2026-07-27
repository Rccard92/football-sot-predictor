"""Create Cecchino Lab historical scan tables (additive, Lab-only).

Revision ID: 20260727120000
Revises: 20260726220000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260727120000"
down_revision: Union[str, Sequence[str], None] = "20260726220000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_lab_historical_scan_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("season_label", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scan_version", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_dataset_id", sa.BigInteger(), nullable=True),
        sa.Column("current_match_id", sa.BigInteger(), nullable=True),
        sa.Column("current_competition", sa.String(length=128), nullable=True),
        sa.Column("matches_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_eligible_core", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_excluded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("quote_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("module_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preflight_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_git_commit", sa.String(length=64), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_lab_hist_scan_runs_season_label",
        "cecchino_lab_historical_scan_runs",
        ["season_label"],
    )
    op.create_index(
        "ix_cecchino_lab_hist_scan_runs_status",
        "cecchino_lab_historical_scan_runs",
        ["status"],
    )
    op.create_index(
        "ix_cecchino_lab_hist_scan_runs_season_status",
        "cecchino_lab_historical_scan_runs",
        ["season_label", "status"],
    )

    op.create_table(
        "cecchino_lab_historical_match_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_name", sa.String(length=128), nullable=False),
        sa.Column("season_label", sa.String(length=32), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team", sa.String(length=128), nullable=True),
        sa.Column("away_team", sa.String(length=128), nullable=True),
        sa.Column("chronological_order", sa.BigInteger(), nullable=True),
        sa.Column("historical_eligibility_status", sa.String(length=64), nullable=False),
        sa.Column("historical_eligibility_reason", sa.String(length=255), nullable=True),
        sa.Column("blocking_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "module_availability_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("input_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cecchino_output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("historical_kpi_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("balance_v5_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "goal_intensity_compatibility_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "purchasability_compatibility_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("quote_sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pre_match_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("pre_match_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlement_status", sa.String(length=32), nullable=True),
        sa.Column(
            "settlement_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["cecchino_lab_historical_scan_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["cecchino_lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lab_match_id"], ["cecchino_lab_matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "lab_match_id", name="uq_cecchino_lab_hist_snap_run_match"),
    )
    op.create_index(
        "ix_cecchino_lab_hist_snap_run_id",
        "cecchino_lab_historical_match_snapshots",
        ["run_id"],
    )
    op.create_index(
        "ix_cecchino_lab_hist_snap_lab_match_id",
        "cecchino_lab_historical_match_snapshots",
        ["lab_match_id"],
    )
    op.create_index(
        "ix_cecchino_lab_hist_snap_eligibility",
        "cecchino_lab_historical_match_snapshots",
        ["historical_eligibility_status"],
    )

    op.create_table(
        "cecchino_lab_historical_market_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("match_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("market_label", sa.String(length=64), nullable=True),
        sa.Column("period", sa.String(length=16), nullable=True),
        sa.Column("line", sa.String(length=16), nullable=True),
        sa.Column("quota_cecchino", sa.Numeric(10, 3), nullable=True),
        sa.Column("prob_cecchino", sa.Numeric(12, 6), nullable=True),
        sa.Column("quota_book", sa.Numeric(10, 3), nullable=True),
        sa.Column("prob_book_raw", sa.Numeric(12, 6), nullable=True),
        sa.Column("prob_book_fair", sa.Numeric(12, 6), nullable=True),
        sa.Column("quote_source_type", sa.String(length=64), nullable=True),
        sa.Column("is_real_book_quote", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_derived_quote", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("derivation_method", sa.String(length=128), nullable=True),
        sa.Column("edge_pct", sa.Numeric(10, 3), nullable=True),
        sa.Column("vantaggio_prob", sa.Numeric(12, 6), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("signal_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("signal_sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evaluation_status", sa.String(length=32), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("profit_1u_real", sa.Numeric(12, 4), nullable=True),
        sa.Column("profit_1u_synthetic", sa.Numeric(12, 4), nullable=True),
        sa.Column("result_reason", sa.String(length=128), nullable=True),
        sa.Column("profit_category", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["cecchino_lab_historical_scan_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["match_snapshot_id"],
            ["cecchino_lab_historical_match_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lab_match_id"], ["cecchino_lab_matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_snapshot_id", "market_key", name="uq_cecchino_lab_hist_mkt_snap_key"
        ),
    )
    op.create_index(
        "ix_cecchino_lab_hist_mkt_run_id",
        "cecchino_lab_historical_market_results",
        ["run_id"],
    )
    op.create_index(
        "ix_cecchino_lab_hist_mkt_market_key",
        "cecchino_lab_historical_market_results",
        ["market_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_lab_hist_mkt_market_key",
        table_name="cecchino_lab_historical_market_results",
    )
    op.drop_index(
        "ix_cecchino_lab_hist_mkt_run_id",
        table_name="cecchino_lab_historical_market_results",
    )
    op.drop_table("cecchino_lab_historical_market_results")
    op.drop_index(
        "ix_cecchino_lab_hist_snap_eligibility",
        table_name="cecchino_lab_historical_match_snapshots",
    )
    op.drop_index(
        "ix_cecchino_lab_hist_snap_lab_match_id",
        table_name="cecchino_lab_historical_match_snapshots",
    )
    op.drop_index(
        "ix_cecchino_lab_hist_snap_run_id",
        table_name="cecchino_lab_historical_match_snapshots",
    )
    op.drop_table("cecchino_lab_historical_match_snapshots")
    op.drop_index(
        "ix_cecchino_lab_hist_scan_runs_season_status",
        table_name="cecchino_lab_historical_scan_runs",
    )
    op.drop_index(
        "ix_cecchino_lab_hist_scan_runs_status",
        table_name="cecchino_lab_historical_scan_runs",
    )
    op.drop_index(
        "ix_cecchino_lab_hist_scan_runs_season_label",
        table_name="cecchino_lab_historical_scan_runs",
    )
    op.drop_table("cecchino_lab_historical_scan_runs")
