"""cecchino pattern discovery: add competition column (league-native discovery)

Revision ID: 20260912120000_patdisc_comp
Revises: 20260912100000_patdisc
Create Date: 2026-09-12 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260912120000_patdisc_comp"
down_revision: Union[str, Sequence[str], None] = "20260912100000_patdisc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_pattern_discovery_runs",
        sa.Column("competition", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_cecchino_pattern_discovery_runs_competition",
        "cecchino_pattern_discovery_runs",
        ["competition"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_pattern_discovery_runs_competition",
        table_name="cecchino_pattern_discovery_runs",
    )
    op.drop_column("cecchino_pattern_discovery_runs", "competition")
