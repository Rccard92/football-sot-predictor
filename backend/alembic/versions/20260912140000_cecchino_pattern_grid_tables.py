"""cecchino pattern grid tables (ricerca esaustiva sequenziale a 4 stadi)

Revision ID: 20260912140000_patgrid
Revises: 20260912120000_patdisc_comp
Create Date: 2026-09-12 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260912140000_patgrid"
down_revision: Union[str, Sequence[str], None] = "20260912120000_patdisc_comp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_pattern_grid_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("competition", sa.String(length=128), nullable=True),
        sa.Column("run_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stages_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stages_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_git_commit", sa.String(length=64), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_pattern_grid_runs_market_key", "cecchino_pattern_grid_runs", ["market_key"]
    )
    op.create_index("ix_cecchino_pattern_grid_runs_status", "cecchino_pattern_grid_runs", ["status"])
    op.create_index(
        "ix_cecchino_pattern_grid_runs_competition", "cecchino_pattern_grid_runs", ["competition"]
    )
    op.create_index(
        "ix_cecchino_pattern_grid_runs_market_status",
        "cecchino_pattern_grid_runs",
        ["market_key", "status"],
    )

    op.create_table(
        "cecchino_pattern_grid_candidates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("grid_run_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(length=32), nullable=False),
        sa.Column("competition", sa.String(length=128), nullable=True),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("filters_text", sa.Text(), nullable=False),
        sa.Column("born_stage", sa.Integer(), nullable=False),
        sa.Column("refined_from_text", sa.Text(), nullable=True),
        sa.Column("per_stage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("final_verdict", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["grid_run_id"], ["cecchino_pattern_grid_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_pattern_grid_candidates_market_key",
        "cecchino_pattern_grid_candidates",
        ["market_key"],
    )
    op.create_index(
        "ix_cecchino_pattern_grid_candidates_run",
        "cecchino_pattern_grid_candidates",
        ["grid_run_id"],
    )
    op.create_index(
        "ix_cecchino_pattern_grid_candidates_final_verdict",
        "cecchino_pattern_grid_candidates",
        ["final_verdict"],
    )
    op.create_index(
        "ix_cecchino_pattern_grid_candidates_market_verdict",
        "cecchino_pattern_grid_candidates",
        ["market_key", "final_verdict"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_pattern_grid_candidates_market_verdict",
        table_name="cecchino_pattern_grid_candidates",
    )
    op.drop_index(
        "ix_cecchino_pattern_grid_candidates_final_verdict",
        table_name="cecchino_pattern_grid_candidates",
    )
    op.drop_index(
        "ix_cecchino_pattern_grid_candidates_run", table_name="cecchino_pattern_grid_candidates"
    )
    op.drop_index(
        "ix_cecchino_pattern_grid_candidates_market_key", table_name="cecchino_pattern_grid_candidates"
    )
    op.drop_table("cecchino_pattern_grid_candidates")

    op.drop_index(
        "ix_cecchino_pattern_grid_runs_market_status", table_name="cecchino_pattern_grid_runs"
    )
    op.drop_index("ix_cecchino_pattern_grid_runs_competition", table_name="cecchino_pattern_grid_runs")
    op.drop_index("ix_cecchino_pattern_grid_runs_status", table_name="cecchino_pattern_grid_runs")
    op.drop_index("ix_cecchino_pattern_grid_runs_market_key", table_name="cecchino_pattern_grid_runs")
    op.drop_table("cecchino_pattern_grid_runs")
