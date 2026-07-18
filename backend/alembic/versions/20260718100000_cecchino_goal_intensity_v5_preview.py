"""Add preview bundle and snapshot tables for Intensità Goal v5 Fase 2A.

Revision ID: 20260718100000
Revises: 20260708120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718100000"
down_revision: Union[str, Sequence[str], None] = "20260708120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_goal_intensity_v5_preview_bundles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("candidate_indices_version", sa.String(length=128), nullable=False),
        sa.Column("candidate_definition_hash", sa.String(length=64), nullable=False),
        sa.Column("fixture_ids_hash", sa.String(length=64), nullable=False),
        sa.Column("targets_hash", sa.String(length=64), nullable=False),
        sa.Column("normalization_method", sa.String(length=64), nullable=False),
        sa.Column("normalization_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("calibration_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_definitions_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrospective_date_from", sa.Date(), nullable=False),
        sa.Column("retrospective_date_to", sa.Date(), nullable=False),
        sa.Column("first_prospective_scan_date", sa.Date(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gi_v5_preview_bundles_version",
        "cecchino_goal_intensity_v5_preview_bundles",
        ["version"],
    )
    op.create_index(
        "ix_gi_v5_preview_bundles_def_hash",
        "cecchino_goal_intensity_v5_preview_bundles",
        ["candidate_definition_hash"],
    )
    op.create_index(
        "ix_gi_v5_preview_bundles_active",
        "cecchino_goal_intensity_v5_preview_bundles",
        ["is_active"],
    )

    op.create_table(
        "cecchino_goal_intensity_v5_preview_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bundle_id", sa.BigInteger(), nullable=False),
        sa.Column("today_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("local_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_source", sa.String(length=32), nullable=True),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("competition_id", sa.BigInteger(), nullable=True),
        sa.Column("home_team_id", sa.BigInteger(), nullable=True),
        sa.Column("away_team_id", sa.BigInteger(), nullable=True),
        sa.Column("home_team_name", sa.String(length=256), nullable=True),
        sa.Column("away_team_name", sa.String(length=256), nullable=True),
        sa.Column("competition_name", sa.String(length=256), nullable=True),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("source_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eligibility_status", sa.String(length=64), nullable=True),
        sa.Column("eligibility_source", sa.String(length=64), nullable=True),
        sa.Column("eligibility_reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feature_status", sa.String(length=64), nullable=True),
        sa.Column("feature_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("history_sample_size", sa.Integer(), nullable=True),
        sa.Column("xg_status", sa.String(length=32), nullable=True),
        sa.Column("xg_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pillar_scores_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidate_scores_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("calibrated_predictions_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("primary_candidate_score", sa.Float(), nullable=True),
        sa.Column("challenger_candidate_score", sa.Float(), nullable=True),
        sa.Column("benchmark_score", sa.Float(), nullable=True),
        sa.Column("diagnostic_score", sa.Float(), nullable=True),
        sa.Column("candidate_definition_hash", sa.String(length=64), nullable=True),
        sa.Column("normalization_hashes_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("no_target_used_in_score", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("snapshot_status", sa.String(length=32), nullable=False),
        sa.Column("preview_status", sa.String(length=32), nullable=False),
        sa.Column("diagnostic_reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revision_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("first_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("goals_home_ft", sa.Integer(), nullable=True),
        sa.Column("goals_away_ft", sa.Integer(), nullable=True),
        sa.Column("total_goals_ft", sa.Integer(), nullable=True),
        sa.Column("goals_ge_2", sa.Integer(), nullable=True),
        sa.Column("goals_ge_3", sa.Integer(), nullable=True),
        sa.Column("btts_ft", sa.Integer(), nullable=True),
        sa.Column("result_attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["bundle_id"],
            ["cecchino_goal_intensity_v5_preview_bundles.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "today_fixture_id", name="uq_gi_v5_preview_bundle_today_fixture"),
    )
    op.create_index(
        "ix_gi_v5_preview_snapshots_today",
        "cecchino_goal_intensity_v5_preview_snapshots",
        ["today_fixture_id"],
    )
    op.create_index(
        "ix_gi_v5_preview_snapshots_scan_date",
        "cecchino_goal_intensity_v5_preview_snapshots",
        ["scan_date"],
    )
    op.create_index(
        "ix_gi_v5_preview_snapshots_status",
        "cecchino_goal_intensity_v5_preview_snapshots",
        ["snapshot_status"],
    )
    op.create_index(
        "ix_gi_v5_preview_snapshots_kickoff",
        "cecchino_goal_intensity_v5_preview_snapshots",
        ["kickoff"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("cecchino_goal_intensity_v5_preview_snapshots")
    op.drop_table("cecchino_goal_intensity_v5_preview_bundles")
