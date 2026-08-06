"""Create Goal Intensity historical benchmark job tables (additive).

Revision ID: 20260806213000
Revises: 20260806200000

Additive only:
- cecchino_lab_goal_intensity_benchmark_jobs
- cecchino_lab_goal_intensity_benchmark_rows

Does not alter historical scan runs/snapshots or GI preview bundle rows.
Downgrade drops only the new tables.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260806213000"
down_revision: Union[str, Sequence[str], None] = "20260806200000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_lab_goal_intensity_benchmark_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("historical_run_id", sa.BigInteger(), nullable=False),
        sa.Column("bundle_id", sa.BigInteger(), nullable=False),
        sa.Column("job_version", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("independence_status", sa.String(length=64), nullable=True),
        sa.Column("job_key", sa.String(length=160), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("requested_sample_size", sa.Integer(), nullable=True),
        sa.Column("total_snapshots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_snapshots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_snapshots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_snapshots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paired_complete", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preflight_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_by_reason_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bundle_definition_hash", sa.String(length=64), nullable=True),
        sa.Column("run_fixture_ids_hash", sa.String(length=64), nullable=True),
        sa.Column("source_git_commit", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
            ["historical_run_id"],
            ["cecchino_lab_historical_scan_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bundle_id"],
            ["cecchino_goal_intensity_v5_preview_bundles.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_key", name="uq_cecchino_lab_gi_bench_jobs_job_key"),
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_jobs_run",
        "cecchino_lab_goal_intensity_benchmark_jobs",
        ["historical_run_id"],
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_jobs_status",
        "cecchino_lab_goal_intensity_benchmark_jobs",
        ["status"],
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_jobs_bundle",
        "cecchino_lab_goal_intensity_benchmark_jobs",
        ["bundle_id"],
    )

    op.create_table(
        "cecchino_lab_goal_intensity_benchmark_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("historical_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=True),
        sa.Column("today_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("local_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("competition_name", sa.String(length=128), nullable=True),
        sa.Column("included_in_main_cohort", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("exclusion_reason", sa.String(length=128), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("prediction_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("target_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evaluation_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            ["job_id"],
            ["cecchino_lab_goal_intensity_benchmark_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "historical_snapshot_id",
            name="uq_cecchino_lab_gi_bench_rows_job_snap",
        ),
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_rows_job",
        "cecchino_lab_goal_intensity_benchmark_rows",
        ["job_id"],
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_rows_snap",
        "cecchino_lab_goal_intensity_benchmark_rows",
        ["historical_snapshot_id"],
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_rows_lab_match",
        "cecchino_lab_goal_intensity_benchmark_rows",
        ["lab_match_id"],
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_rows_competition",
        "cecchino_lab_goal_intensity_benchmark_rows",
        ["competition_name"],
    )
    op.create_index(
        "ix_cecchino_lab_gi_bench_rows_kickoff",
        "cecchino_lab_goal_intensity_benchmark_rows",
        ["kickoff_at"],
    )


def downgrade() -> None:
    op.drop_table("cecchino_lab_goal_intensity_benchmark_rows")
    op.drop_table("cecchino_lab_goal_intensity_benchmark_jobs")
