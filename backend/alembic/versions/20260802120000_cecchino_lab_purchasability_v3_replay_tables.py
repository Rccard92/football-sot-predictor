"""Create Cecchino Lab purchasability V3 replay tables (additive, Lab-only).

Revision ID: 20260802120000
Revises: 20260727180000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802120000"
down_revision: Union[str, Sequence[str], None] = "20260727180000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_lab_purchasability_v3_replay_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_scan_run_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("replay_schema_version", sa.String(length=96), nullable=False),
        sa.Column("replay_engine_version", sa.String(length=96), nullable=False),
        sa.Column("candidate_version", sa.String(length=96), nullable=False),
        sa.Column("formula_version", sa.String(length=96), nullable=False),
        sa.Column("audit_version", sa.String(length=96), nullable=False),
        sa.Column("preflight_schema_version", sa.String(length=96), nullable=False),
        sa.Column("integrity_policy_version", sa.String(length=96), nullable=False),
        sa.Column("source_scan_git_commit", sa.String(length=64), nullable=True),
        sa.Column("runtime_git_commit", sa.String(length=64), nullable=True),
        sa.Column("runtime_git_commit_source", sa.String(length=64), nullable=True),
        sa.Column("source_scan_version", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshots_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshots_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluations_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluations_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("current_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("current_chronological_order", sa.BigInteger(), nullable=True),
        sa.Column("current_competition", sa.String(length=128), nullable=True),
        sa.Column("scored_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gate_failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unavailable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_applicable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unclassified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exact_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("non_replayable_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("real_quote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derived_quote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unavailable_quote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("real_performance_ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "synthetic_performance_ready_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("performance_missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("preflight_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            ["source_scan_run_id"],
            ["cecchino_lab_historical_scan_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_cecchino_lab_p3_replay_runs_idempotency"),
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_runs_status",
        "cecchino_lab_purchasability_v3_replay_runs",
        ["status"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_runs_source_scan",
        "cecchino_lab_purchasability_v3_replay_runs",
        ["source_scan_run_id"],
    )

    op.create_table(
        "cecchino_lab_purchasability_v3_replay_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("replay_run_id", sa.BigInteger(), nullable=False),
        sa.Column("source_scan_run_id", sa.BigInteger(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("source_market_result_id", sa.BigInteger(), nullable=True),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=True),
        sa.Column("competition_name", sa.String(length=128), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chronological_order", sa.BigInteger(), nullable=True),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("market_family", sa.String(length=64), nullable=True),
        sa.Column("quote_source", sa.String(length=64), nullable=True),
        sa.Column("quote_quality", sa.String(length=32), nullable=True),
        sa.Column("performance_type", sa.String(length=64), nullable=True),
        sa.Column("is_real_book_quote", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_derived_quote", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("derivation_method", sa.String(length=128), nullable=True),
        sa.Column("quota_book", sa.Numeric(10, 3), nullable=True),
        sa.Column("quota_cecchino", sa.Numeric(10, 3), nullable=True),
        sa.Column("prob_book_raw", sa.Numeric(12, 6), nullable=True),
        sa.Column("prob_book_fair", sa.Numeric(12, 6), nullable=True),
        sa.Column("prob_cecchino", sa.Numeric(12, 6), nullable=True),
        sa.Column("edge_pct", sa.Numeric(10, 3), nullable=True),
        sa.Column("vantaggio_prob", sa.Numeric(12, 6), nullable=True),
        sa.Column("calculation_status", sa.String(length=48), nullable=True),
        sa.Column("gate_status", sa.String(length=48), nullable=True),
        sa.Column(
            "gate_reason_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("raw_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("score_class", sa.String(length=32), nullable=True),
        sa.Column("value_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("quality_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("total_penalty", sa.Numeric(12, 4), nullable=True),
        sa.Column("probability_risk_penalty", sa.Numeric(12, 4), nullable=True),
        sa.Column("opposite_market_pressure_penalty", sa.Numeric(12, 4), nullable=True),
        sa.Column("extreme_divergence_penalty", sa.Numeric(12, 4), nullable=True),
        sa.Column("family_ambiguity_penalty", sa.Numeric(12, 4), nullable=True),
        sa.Column("quote_quality_penalty", sa.Numeric(12, 4), nullable=True),
        sa.Column("opposite_market_key", sa.String(length=32), nullable=True),
        sa.Column("opposite_fair_probability", sa.Numeric(12, 6), nullable=True),
        sa.Column("selected_is_family_edge_leader", sa.Boolean(), nullable=True),
        sa.Column("family_edge_gap_or_deficit", sa.Numeric(12, 4), nullable=True),
        sa.Column("calculation_quality", sa.String(length=48), nullable=True),
        sa.Column("reason_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("performance_evaluation_status", sa.String(length=64), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("profit_1u_real", sa.Numeric(12, 4), nullable=True),
        sa.Column("profit_1u_synthetic", sa.Numeric(12, 4), nullable=True),
        sa.Column("result_reason", sa.String(length=128), nullable=True),
        sa.Column("source_pre_match_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_pre_match_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("formula_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "formula_payload_fields_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("pre_match_only", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "post_match_fields_excluded", sa.Boolean(), nullable=False, server_default="true"
        ),
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
            ["replay_run_id"],
            ["cecchino_lab_purchasability_v3_replay_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_scan_run_id"],
            ["cecchino_lab_historical_scan_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "replay_run_id",
            "source_snapshot_id",
            "market_key",
            name="uq_cecchino_lab_p3_replay_res_run_snap_mkt",
        ),
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_run_id",
        "cecchino_lab_purchasability_v3_replay_results",
        ["replay_run_id"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_market_key",
        "cecchino_lab_purchasability_v3_replay_results",
        ["market_key"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_market_family",
        "cecchino_lab_purchasability_v3_replay_results",
        ["market_family"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_score",
        "cecchino_lab_purchasability_v3_replay_results",
        ["score"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_gate_status",
        "cecchino_lab_purchasability_v3_replay_results",
        ["gate_status"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_competition",
        "cecchino_lab_purchasability_v3_replay_results",
        ["competition_name"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_kickoff",
        "cecchino_lab_purchasability_v3_replay_results",
        ["kickoff_at"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_real_quote",
        "cecchino_lab_purchasability_v3_replay_results",
        ["is_real_book_quote"],
    )
    op.create_index(
        "ix_cecchino_lab_p3_replay_res_derived_quote",
        "cecchino_lab_purchasability_v3_replay_results",
        ["is_derived_quote"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_derived_quote",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_real_quote",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_kickoff",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_competition",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_gate_status",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_score",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_market_family",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_market_key",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_res_run_id",
        table_name="cecchino_lab_purchasability_v3_replay_results",
    )
    op.drop_table("cecchino_lab_purchasability_v3_replay_results")

    op.drop_index(
        "ix_cecchino_lab_p3_replay_runs_source_scan",
        table_name="cecchino_lab_purchasability_v3_replay_runs",
    )
    op.drop_index(
        "ix_cecchino_lab_p3_replay_runs_status",
        table_name="cecchino_lab_purchasability_v3_replay_runs",
    )
    op.drop_table("cecchino_lab_purchasability_v3_replay_runs")
