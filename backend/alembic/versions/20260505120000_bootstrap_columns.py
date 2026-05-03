"""bootstrap league season team fixture columns

Revision ID: 20260505120000
Revises: 20260504100000
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260505120000"
down_revision: Union[str, Sequence[str], None] = "20260504100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leagues", sa.Column("logo_url", sa.String(length=512), nullable=True))
    op.add_column("seasons", sa.Column("label", sa.String(length=32), nullable=True))
    op.add_column(
        "seasons",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("teams", sa.Column("code", sa.String(length=16), nullable=True))
    op.add_column("teams", sa.Column("country", sa.String(length=128), nullable=True))
    op.add_column("teams", sa.Column("founded", sa.Integer(), nullable=True))
    op.add_column(
        "teams",
        sa.Column("national", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("teams", sa.Column("venue_name", sa.String(length=255), nullable=True))
    op.add_column("teams", sa.Column("venue_city", sa.String(length=128), nullable=True))
    op.add_column("fixtures", sa.Column("round", sa.String(length=64), nullable=True))
    op.add_column("fixtures", sa.Column("referee", sa.String(length=255), nullable=True))
    op.add_column("fixtures", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("fixtures", sa.Column("status_long", sa.String(length=128), nullable=True))
    op.add_column("fixtures", sa.Column("elapsed", sa.Integer(), nullable=True))
    op.add_column("fixtures", sa.Column("venue_name", sa.String(length=255), nullable=True))
    op.add_column("fixtures", sa.Column("venue_city", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("fixtures", "venue_city")
    op.drop_column("fixtures", "venue_name")
    op.drop_column("fixtures", "elapsed")
    op.drop_column("fixtures", "status_long")
    op.drop_column("fixtures", "timezone")
    op.drop_column("fixtures", "referee")
    op.drop_column("fixtures", "round")
    op.drop_column("teams", "venue_city")
    op.drop_column("teams", "venue_name")
    op.drop_column("teams", "national")
    op.drop_column("teams", "founded")
    op.drop_column("teams", "country")
    op.drop_column("teams", "code")
    op.drop_column("seasons", "is_current")
    op.drop_column("seasons", "label")
    op.drop_column("leagues", "logo_url")
