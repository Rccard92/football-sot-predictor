"""Migration: snapshot aggregati League Pattern Analysis (append-only)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260831180000_lpa_snap"
down_revision = "20260828120000_quote_obs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cecchino_lab_league_pattern_analysis_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_version", sa.String(length=96), nullable=False),
        sa.Column("analysis_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("source_run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_seasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scan_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preset_registry_version", sa.String(length=96), nullable=False),
        sa.Column("source_git_commit", sa.String(length=64), nullable=True),
        sa.Column(
            "analysis_dataset_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("future_oos_season", sa.String(length=32), nullable=False),
        sa.Column(
            "future_oos_included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "source_enrichment_batch_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "market_universe_version",
            sa.String(length=64),
            nullable=False,
            server_default="base_v1",
        ),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "competition_regimes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "global_patterns_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "pattern_league_matrix_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "specializations_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "incompatibilities_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "league_native_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "methodology_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
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
        "ix_lpa_snap_analysis_version",
        "cecchino_lab_league_pattern_analysis_snapshots",
        ["analysis_version"],
        unique=False,
    )
    op.create_index(
        "ix_lpa_snap_status",
        "cecchino_lab_league_pattern_analysis_snapshots",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_lpa_snap_version_status_generated",
        "cecchino_lab_league_pattern_analysis_snapshots",
        ["analysis_version", "status", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lpa_snap_version_status_generated",
        table_name="cecchino_lab_league_pattern_analysis_snapshots",
    )
    op.drop_index(
        "ix_lpa_snap_status",
        table_name="cecchino_lab_league_pattern_analysis_snapshots",
    )
    op.drop_index(
        "ix_lpa_snap_analysis_version",
        table_name="cecchino_lab_league_pattern_analysis_snapshots",
    )
    op.drop_table("cecchino_lab_league_pattern_analysis_snapshots")
