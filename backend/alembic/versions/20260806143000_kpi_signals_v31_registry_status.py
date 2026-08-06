"""Add purchasability_v31_registry_status to KPI signal activations

Revision ID: 20260806143000
Revises: 20260806120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260806143000"
down_revision: Union[str, Sequence[str], None] = "20260806120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "cecchino_kpi_signal_activations"
_COLUMN = "purchasability_v31_registry_status"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_column(_TABLE, _COLUMN)
