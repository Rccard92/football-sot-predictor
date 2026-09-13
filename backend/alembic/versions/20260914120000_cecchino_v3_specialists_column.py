"""cecchino v3 fase 2: opinioni degli specialisti per partita

Revision ID: 20260914120000_v3_specialists
Revises: 20260914090000_v3_phase1
Create Date: 2026-09-14 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914120000_v3_specialists"
down_revision: Union[str, Sequence[str], None] = "20260914090000_v3_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_v3_match_predictions",
        sa.Column("specialists_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cecchino_v3_match_predictions", "specialists_json")
