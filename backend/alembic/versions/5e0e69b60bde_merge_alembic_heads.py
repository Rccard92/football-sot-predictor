"""merge alembic heads

Revision ID: 5e0e69b60bde
Revises: 20260609180000, 20260620120000
Create Date: 2026-06-11 18:40:41.612527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e0e69b60bde'
down_revision: Union[str, Sequence[str], None] = ('20260609180000', '20260620120000')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
