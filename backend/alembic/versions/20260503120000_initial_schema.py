"""initial_schema

Revision ID: 20260503120000
Revises:
Create Date: 2026-05-03

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260503120000"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
