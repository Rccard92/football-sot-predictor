"""Tabella analisi: note dell'analista per partita (solo additiva, una tabella nuova).

Revision ID: 20261105100000_analyst_notes
Revises: 20261031090000_v5_resettle
Create Date: 2026-11-05 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261105100000_analyst_notes"
down_revision: Union[str, Sequence[str], None] = "20261031090000_v5_resettle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "analyst_match_notes" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "analyst_match_notes",
        sa.Column("id", pk, primary_key=True, autoincrement=True),
        sa.Column("user_id", pk, sa.ForeignKey("app_users.id"), nullable=False, index=True),
        sa.Column("today_fixture_id", pk, nullable=False, index=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "today_fixture_id", name="uq_analyst_match_notes_user_fixture"),
    )


def downgrade() -> None:
    op.drop_table("analyst_match_notes")
