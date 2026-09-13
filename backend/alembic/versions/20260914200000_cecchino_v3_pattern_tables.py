"""cecchino v3 passo 3c: pattern V3 con protocollo V2

Revision ID: 20260914200000_v3_patterns
Revises: 20260914180000_v3_evaluator
Create Date: 2026-09-14 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914200000_v3_patterns"
down_revision: Union[str, Sequence[str], None] = "20260914180000_v3_evaluator"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_v3_pattern_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_run_id", sa.BigInteger(), sa.ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "index_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_index_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("config_json", postgresql.JSONB(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
        sa.Column("source_git_commit", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cecchino_v3_patterns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "pattern_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_pattern_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market_key", sa.String(32), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(512), nullable=False),
        sa.Column("conditions_json", postgresql.JSONB(), nullable=False),
        sa.Column("discovery_n", sa.Integer(), nullable=False),
        sa.Column("discovery_roi", sa.Numeric(10, 5), nullable=False),
        sa.Column("seasons_json", postgresql.JSONB(), nullable=False),
        sa.Column("confirmed_all", sa.Boolean(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_cecchino_v3_pattern_run_market", "cecchino_v3_patterns", ["pattern_run_id", "market_key"])


def downgrade() -> None:
    op.drop_index("ix_cecchino_v3_pattern_run_market", table_name="cecchino_v3_patterns")
    op.drop_table("cecchino_v3_patterns")
    op.drop_table("cecchino_v3_pattern_runs")
