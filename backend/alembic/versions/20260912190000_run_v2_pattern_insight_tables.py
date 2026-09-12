"""cecchino run v2 pattern insight: nuove tabelle job + candidati

Revision ID: 20260912190000_pi_tables
Revises: 20260912180000_patgrid_wq
Create Date: 2026-09-12 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260912190000_pi_tables"
down_revision: Union[str, Sequence[str], None] = "20260912180000_patgrid_wq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_run_v2_pattern_insight_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_v2_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_run_v2_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("targets_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("targets_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_target_label", sa.String(128), nullable=True),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_git_commit", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "cecchino_run_v2_pattern_insight_candidates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "insight_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_run_v2_pattern_insight_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_key", sa.String(32), nullable=False),
        sa.Column("target_label", sa.String(128), nullable=False),
        sa.Column("threshold", sa.Numeric(6, 2), nullable=True),
        sa.Column("filters_json", postgresql.JSONB(), nullable=False),
        sa.Column("filters_text", sa.Text(), nullable=False),
        sa.Column("filters_text_human", sa.Text(), nullable=False),
        sa.Column("refined_from_text", sa.Text(), nullable=True),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("roi_pct", sa.Numeric(8, 3), nullable=True),
        sa.Column("avg_quota", sa.Numeric(6, 3), nullable=True),
        sa.Column("baseline_win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("deviation_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_cecchino_run_v2_pi_cand_run",
        "cecchino_run_v2_pattern_insight_candidates",
        ["insight_run_id"],
    )
    op.create_index(
        "ix_cecchino_run_v2_pi_cand_target",
        "cecchino_run_v2_pattern_insight_candidates",
        ["target_type", "target_key"],
    )
    op.create_index(
        "ix_cecchino_run_v2_pi_cand_roi",
        "cecchino_run_v2_pattern_insight_candidates",
        ["roi_pct"],
    )
    op.create_index(
        "ix_cecchino_run_v2_pi_cand_deviation",
        "cecchino_run_v2_pattern_insight_candidates",
        ["deviation_pct"],
    )


def downgrade() -> None:
    op.drop_table("cecchino_run_v2_pattern_insight_candidates")
    op.drop_table("cecchino_run_v2_pattern_insight_runs")
