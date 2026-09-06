"""add historical bet365 enrichment odds

Revision ID: df845d7b484f
Revises: 20260831180000_lpa_snap
Create Date: 2026-09-06 18:44:54.334774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df845d7b484f'
down_revision: Union[str, Sequence[str], None] = '20260831180000_lpa_snap'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
