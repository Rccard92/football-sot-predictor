"""cecchino_today blocking_reasons_json

Revision ID: 20260615120000
Revises: 20260614120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260615120000"
down_revision: Union[str, Sequence[str], None] = "20260614120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "cecchino_today_fixtures",
        sa.Column("blocking_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_column("cecchino_today_fixtures", "blocking_reasons_json")
