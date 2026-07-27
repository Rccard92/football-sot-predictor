"""Add Cecchino Lab scan git revision columns.

Revision ID: 20260727180000
Revises: 20260727120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260727180000"
down_revision: Union[str, Sequence[str], None] = "20260727120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_lab_historical_scan_runs",
        sa.Column("source_git_commit_source", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "cecchino_lab_historical_scan_runs",
        sa.Column("source_revision_status", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cecchino_lab_historical_scan_runs", "source_revision_status")
    op.drop_column("cecchino_lab_historical_scan_runs", "source_git_commit_source")
