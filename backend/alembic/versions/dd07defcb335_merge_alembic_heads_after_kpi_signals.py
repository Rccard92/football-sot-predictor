"""merge alembic heads after kpi signals

Revision ID: dd07defcb335
Revises: 20260704120000, 5e0e69b60bde
Create Date: 2026-07-04 00:09:37.223957

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd07defcb335'
down_revision: Union[str, Sequence[str], None] = ('20260704120000', '5e0e69b60bde')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
