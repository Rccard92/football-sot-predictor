"""cecchino v3 passo 4: test finale sulla stagione sotto chiave

Revision ID: 20260914220000_v3_final
Revises: 20260914200000_v3_patterns
Create Date: 2026-09-14 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914220000_v3_final"
down_revision: Union[str, Sequence[str], None] = "20260914200000_v3_patterns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_v3_final_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
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


def downgrade() -> None:
    op.drop_table("cecchino_v3_final_runs")
