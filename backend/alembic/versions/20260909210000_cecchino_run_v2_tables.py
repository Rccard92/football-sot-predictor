"""cecchino run v2 tables (additive only, RUN V1 untouched)

Revision ID: 20260909210000_run_v2
Revises: 99102f74d1c9
Create Date: 2026-09-09 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260909210000_run_v2"
down_revision: Union[str, Sequence[str], None] = "99102f74d1c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_run_v2_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_scope", sa.String(length=32), nullable=False),
        sa.Column("max_matches", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matches_total", sa.Integer(), nullable=False),
        sa.Column("matches_processed", sa.Integer(), nullable=False),
        sa.Column("matches_error", sa.Integer(), nullable=False),
        sa.Column("market_rows_written", sa.Integer(), nullable=False),
        sa.Column("leakage_violations", sa.Integer(), nullable=False),
        sa.Column("progress_pct", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("min_kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_competition", sa.String(length=128), nullable=True),
        sa.Column("current_lab_match_id", sa.BigInteger(), nullable=True),
        sa.Column("last_processed_kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("module_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coverage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("leakage_audit_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_git_commit", sa.String(length=64), nullable=True),
        sa.Column("source_git_commit_source", sa.String(length=64), nullable=True),
        sa.Column("source_revision_status", sa.String(length=32), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
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
    op.create_index("ix_cecchino_run_v2_runs_status", "cecchino_run_v2_runs", ["status"])
    op.create_index(
        "ix_cecchino_run_v2_runs_version_status",
        "cecchino_run_v2_runs",
        ["run_version", "status"],
    )

    op.create_table(
        "cecchino_run_v2_match_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_name", sa.String(length=128), nullable=False),
        sa.Column("competition_id", sa.BigInteger(), nullable=True),
        sa.Column("division_code", sa.String(length=16), nullable=True),
        sa.Column("season_label", sa.String(length=32), nullable=False),
        sa.Column("season_start_year", sa.Integer(), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team", sa.String(length=128), nullable=True),
        sa.Column("away_team", sa.String(length=128), nullable=True),
        sa.Column("referee", sa.String(length=128), nullable=True),
        sa.Column("chronological_order", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("eligibility_status", sa.String(length=64), nullable=True),
        sa.Column("eligibility_reason", sa.String(length=255), nullable=True),
        sa.Column("pre_match_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pre_match_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("pre_match_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cecchino_output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("goal_markets_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("kpi_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("signals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("balance_v5_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("goal_intensity_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("purchasability_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quote_bundle_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "extra_stats_prematch_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("actuals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leakage_audit_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("history_count", sa.Integer(), nullable=False),
        sa.Column("latest_history_kickoff_used", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pre_match_cutoff_ok", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["run_id"], ["cecchino_run_v2_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["cecchino_lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lab_match_id"], ["cecchino_lab_matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "lab_match_id", name="uq_cecchino_run_v2_snap_run_match"),
    )
    op.create_index(
        "ix_cecchino_run_v2_snap_run_id", "cecchino_run_v2_match_snapshots", ["run_id"]
    )
    op.create_index(
        "ix_cecchino_run_v2_snap_lab_match_id",
        "cecchino_run_v2_match_snapshots",
        ["lab_match_id"],
    )
    op.create_index(
        "ix_cecchino_run_v2_snap_run_kickoff",
        "cecchino_run_v2_match_snapshots",
        ["run_id", "kickoff_at"],
    )
    op.create_index(
        "ix_cecchino_run_v2_snap_run_competition",
        "cecchino_run_v2_match_snapshots",
        ["run_id", "competition_name"],
    )

    op.create_table(
        "cecchino_run_v2_market_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("match_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("market_label", sa.String(length=64), nullable=True),
        sa.Column("market_family", sa.String(length=32), nullable=True),
        sa.Column("period", sa.String(length=16), nullable=True),
        sa.Column("line", sa.String(length=16), nullable=True),
        sa.Column("observation_layer", sa.String(length=32), nullable=False),
        sa.Column("prediction", sa.String(length=32), nullable=True),
        sa.Column("probability", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("quota_cecchino", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("kpi_rating", sa.Integer(), nullable=True),
        sa.Column("edge_pct", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("vantaggio_prob", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("signal_active", sa.Boolean(), nullable=False),
        sa.Column("signal_sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("buyability_score", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("buyability_class", sa.String(length=48), nullable=True),
        sa.Column("equilibrium_state", sa.String(length=48), nullable=True),
        sa.Column("goal_intensity_score", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("market_available", sa.Boolean(), nullable=False),
        sa.Column("market_quote_available", sa.Boolean(), nullable=False),
        sa.Column("quota_book", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("prob_book_raw", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("prob_book_fair", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("is_real_quote", sa.Boolean(), nullable=False),
        sa.Column("is_derived_quote", sa.Boolean(), nullable=False),
        sa.Column("derivation_method", sa.String(length=128), nullable=True),
        sa.Column("quote_source", sa.String(length=64), nullable=True),
        sa.Column("quote_type", sa.String(length=32), nullable=True),
        sa.Column("source_column", sa.String(length=64), nullable=True),
        sa.Column("quote_snapshot_type", sa.String(length=32), nullable=True),
        sa.Column("pre_match_input_safe", sa.Boolean(), nullable=False),
        sa.Column("used_for_prediction", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("flat_stake_profit", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("result_reason", sa.String(length=128), nullable=True),
        sa.Column("economic_benchmark_value", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("economic_benchmark_profit", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("economic_benchmark_roi", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("economic_observation_only", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["run_id"], ["cecchino_run_v2_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["match_snapshot_id"],
            ["cecchino_run_v2_match_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lab_match_id"], ["cecchino_lab_matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_snapshot_id",
            "market_key",
            "observation_layer",
            name="uq_cecchino_run_v2_mkt_snap_key_layer",
        ),
    )
    op.create_index("ix_cecchino_run_v2_mkt_run_id", "cecchino_run_v2_market_results", ["run_id"])
    op.create_index(
        "ix_cecchino_run_v2_mkt_lab_match_id",
        "cecchino_run_v2_market_results",
        ["lab_match_id"],
    )
    op.create_index(
        "ix_cecchino_run_v2_mkt_run_key_layer",
        "cecchino_run_v2_market_results",
        ["run_id", "market_key", "observation_layer"],
    )


def downgrade() -> None:
    op.drop_index("ix_cecchino_run_v2_mkt_run_key_layer", table_name="cecchino_run_v2_market_results")
    op.drop_index("ix_cecchino_run_v2_mkt_lab_match_id", table_name="cecchino_run_v2_market_results")
    op.drop_index("ix_cecchino_run_v2_mkt_run_id", table_name="cecchino_run_v2_market_results")
    op.drop_table("cecchino_run_v2_market_results")

    op.drop_index(
        "ix_cecchino_run_v2_snap_run_competition", table_name="cecchino_run_v2_match_snapshots"
    )
    op.drop_index(
        "ix_cecchino_run_v2_snap_run_kickoff", table_name="cecchino_run_v2_match_snapshots"
    )
    op.drop_index(
        "ix_cecchino_run_v2_snap_lab_match_id", table_name="cecchino_run_v2_match_snapshots"
    )
    op.drop_index("ix_cecchino_run_v2_snap_run_id", table_name="cecchino_run_v2_match_snapshots")
    op.drop_table("cecchino_run_v2_match_snapshots")

    op.drop_index("ix_cecchino_run_v2_runs_version_status", table_name="cecchino_run_v2_runs")
    op.drop_index("ix_cecchino_run_v2_runs_status", table_name="cecchino_run_v2_runs")
    op.drop_table("cecchino_run_v2_runs")
