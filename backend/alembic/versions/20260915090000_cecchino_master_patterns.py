"""master pattern: pattern vincenti 4/4 per modello

Revision ID: 20260915090000_master_patterns
Revises: 20260914220000_v3_final
Create Date: 2026-09-15 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915090000_master_patterns"
down_revision: Union[str, Sequence[str], None] = "20260914220000_v3_final"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_master_pattern_builds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("model", sa.String(16), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
        sa.Column("source_git_commit", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cecchino_master_patterns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "build_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_master_pattern_builds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(16), nullable=False),
        sa.Column("engine_version", sa.String(128), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_key", sa.String(32), nullable=False),
        sa.Column("target_label", sa.String(128), nullable=False),
        sa.Column("threshold", sa.Numeric(6, 2), nullable=True),
        sa.Column("direction", sa.Integer(), nullable=False),
        sa.Column("market_label", sa.String(128), nullable=False),
        sa.Column("conditions_json", postgresql.JSONB(), nullable=False),
        sa.Column("conditions_text", sa.Text(), nullable=False),
        sa.Column("seasons_json", postgresql.JSONB(), nullable=False),
        sa.Column("total_n", sa.Integer(), nullable=False),
        sa.Column("total_wins", sa.Integer(), nullable=False),
        sa.Column("win_rate_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("profit_units", sa.Numeric(10, 2), nullable=True),
        sa.Column("roi_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("avg_quota", sa.Numeric(7, 3), nullable=True),
        sa.Column("avg_deviation_pct", sa.Numeric(7, 2), nullable=True),
        sa.Column("chance_p", sa.Numeric(12, 8), nullable=True),
    )
    op.create_index(
        "ix_cecchino_master_pattern_build_type",
        "cecchino_master_patterns",
        ["build_id", "target_type", "target_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_cecchino_master_pattern_build_type", table_name="cecchino_master_patterns")
    op.drop_table("cecchino_master_patterns")
    op.drop_table("cecchino_master_pattern_builds")
