"""cecchino_today_scan_jobs

Revision ID: 20260616120000
Revises: 20260615120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260616120000"
down_revision: Union[str, Sequence[str], None] = "20260615120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_today_scan_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Rome"),
        sa.Column("force_rescan", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("fixtures_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fixtures_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("odds_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_cecchino_today_scan_jobs_job_id"),
    )
    op.create_index(
        "ix_cecchino_today_scan_jobs_scan_date_status",
        "cecchino_today_scan_jobs",
        ["scan_date", "status"],
    )
    op.create_index("ix_cecchino_today_scan_jobs_scan_date", "cecchino_today_scan_jobs", ["scan_date"])
    op.create_index("ix_cecchino_today_scan_jobs_status", "cecchino_today_scan_jobs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_cecchino_today_scan_jobs_status", table_name="cecchino_today_scan_jobs")
    op.drop_index("ix_cecchino_today_scan_jobs_scan_date", table_name="cecchino_today_scan_jobs")
    op.drop_index("ix_cecchino_today_scan_jobs_scan_date_status", table_name="cecchino_today_scan_jobs")
    op.drop_table("cecchino_today_scan_jobs")
