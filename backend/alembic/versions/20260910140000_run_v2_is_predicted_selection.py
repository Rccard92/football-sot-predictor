"""cecchino run v2: is_predicted_selection on market results

Revision ID: 20260910140000_run_v2_ips
Revises: 20260909210000_run_v2
Create Date: 2026-09-10 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260910140000_run_v2_ips"
down_revision: Union[str, Sequence[str], None] = "20260909210000_run_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_run_v2_market_results",
        sa.Column(
            "is_predicted_selection",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("cecchino_run_v2_market_results", "is_predicted_selection")
