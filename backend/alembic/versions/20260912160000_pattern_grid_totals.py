"""cecchino pattern grid: add total (4-year pooled) stats + human label

Revision ID: 20260912160000_patgrid_tot
Revises: 20260912140000_patgrid
Create Date: 2026-09-12 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260912160000_patgrid_tot"
down_revision: Union[str, Sequence[str], None] = "20260912140000_patgrid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_pattern_grid_candidates",
        sa.Column("filters_text_human", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "cecchino_pattern_grid_candidates", sa.Column("total_n", sa.Integer(), nullable=True)
    )
    op.add_column(
        "cecchino_pattern_grid_candidates",
        sa.Column("total_win_rate_pct", sa.Numeric(6, 3), nullable=True),
    )
    op.add_column(
        "cecchino_pattern_grid_candidates",
        sa.Column("total_roi_pct", sa.Numeric(8, 3), nullable=True),
    )
    op.create_index(
        "ix_cecchino_pattern_grid_candidates_total_roi",
        "cecchino_pattern_grid_candidates",
        ["total_roi_pct"],
    )
    op.alter_column("cecchino_pattern_grid_candidates", "filters_text_human", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_pattern_grid_candidates_total_roi",
        table_name="cecchino_pattern_grid_candidates",
    )
    op.drop_column("cecchino_pattern_grid_candidates", "total_roi_pct")
    op.drop_column("cecchino_pattern_grid_candidates", "total_win_rate_pct")
    op.drop_column("cecchino_pattern_grid_candidates", "total_n")
    op.drop_column("cecchino_pattern_grid_candidates", "filters_text_human")
