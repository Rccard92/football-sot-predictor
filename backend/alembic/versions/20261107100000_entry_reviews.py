"""Diario analisi: revisione delle giocate dopo la partita (solo additiva, una tabella nuova).

Revision ID: 20261107100000_entry_reviews
Revises: 20261105100000_analyst_notes
Create Date: 2026-11-07 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261107100000_entry_reviews"
down_revision: Union[str, Sequence[str], None] = "20261105100000_analyst_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "analyst_entry_reviews" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "analyst_entry_reviews",
        sa.Column("id", pk, primary_key=True, autoincrement=True),
        sa.Column("entry_id", pk, sa.ForeignKey("analyst_entries.id"), nullable=False, index=True),
        sa.Column("user_id", pk, sa.ForeignKey("app_users.id"), nullable=False, index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("entry_id", "user_id", name="uq_analyst_entry_reviews_entry_user"),
    )


def downgrade() -> None:
    op.drop_table("analyst_entry_reviews")
