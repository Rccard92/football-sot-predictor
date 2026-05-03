"""prediction_backtests squared_error and details

Revision ID: 20260504100000
Revises: 20260503120000
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260504100000"
down_revision: Union[str, Sequence[str], None] = "20260503120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prediction_backtests",
        sa.Column(
            "squared_error",
            sa.Double(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "prediction_backtests",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.alter_column("prediction_backtests", "squared_error", server_default=None)


def downgrade() -> None:
    op.drop_column("prediction_backtests", "details")
    op.drop_column("prediction_backtests", "squared_error")
