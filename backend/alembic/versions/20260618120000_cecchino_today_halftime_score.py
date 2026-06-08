"""cecchino_today halftime score fields

Revision ID: 20260618120000
Revises: 20260617120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260618120000"
down_revision: Union[str, Sequence[str], None] = "20260617120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column("cecchino_today_fixtures", sa.Column("score_halftime_home", sa.Integer(), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("score_halftime_away", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_column("cecchino_today_fixtures", "score_halftime_away")
    op.drop_column("cecchino_today_fixtures", "score_halftime_home")
