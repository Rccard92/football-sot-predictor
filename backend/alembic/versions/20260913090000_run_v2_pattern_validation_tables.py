"""cecchino run v2 pattern validation: verifica fuori campione dei pattern

Revision ID: 20260913090000_pval_tables
Revises: 20260912190000_pi_tables
Create Date: 2026-09-13 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260913090000_pval_tables"
down_revision: Union[str, Sequence[str], None] = "20260912190000_pi_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_run_v2_pattern_validation_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "insight_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_run_v2_pattern_insight_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_v2_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_run_v2_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("season_label", sa.String(32), nullable=True),
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
        sa.Column("source_git_commit", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "cecchino_run_v2_pattern_validations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "validation_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_run_v2_pattern_validation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_run_v2_pattern_insight_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("roi_pct", sa.Numeric(9, 3), nullable=True),
        sa.Column("profit_units", sa.Numeric(10, 3), nullable=True),
        sa.Column("avg_quota", sa.Numeric(6, 3), nullable=True),
        sa.Column("baseline_win_rate_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("deviation_pct", sa.Numeric(7, 3), nullable=True),
        sa.Column("verdict", sa.String(24), nullable=False),
        sa.Column("null_confirm_prob", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_cecchino_run_v2_pval_run_verdict",
        "cecchino_run_v2_pattern_validations",
        ["validation_run_id", "verdict"],
    )
    op.create_index(
        "ix_cecchino_run_v2_pval_candidate",
        "cecchino_run_v2_pattern_validations",
        ["candidate_id"],
    )


def downgrade() -> None:
    op.drop_table("cecchino_run_v2_pattern_validations")
    op.drop_table("cecchino_run_v2_pattern_validation_runs")
