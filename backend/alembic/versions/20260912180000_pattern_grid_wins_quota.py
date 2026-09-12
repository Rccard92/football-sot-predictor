"""cecchino pattern grid: add total wins + total average odds

Revision ID: 20260912180000_patgrid_wq
Revises: 20260912160000_patgrid_tot
Create Date: 2026-09-12 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260912180000_patgrid_wq"
down_revision: Union[str, Sequence[str], None] = "20260912160000_patgrid_tot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_pattern_grid_candidates", sa.Column("total_wins", sa.Integer(), nullable=True)
    )
    op.add_column(
        "cecchino_pattern_grid_candidates",
        sa.Column("total_avg_quota", sa.Numeric(6, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cecchino_pattern_grid_candidates", "total_avg_quota")
    op.drop_column("cecchino_pattern_grid_candidates", "total_wins")
