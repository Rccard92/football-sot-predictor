"""Diario analisi: regole di acquisto (solo additiva: una tabella e due colonne nuove, nullable).

Revision ID: 20261107140000_analyst_rules
Revises: 20261107100000_entry_reviews
Create Date: 2026-11-07 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261107140000_analyst_rules"
down_revision: Union[str, Sequence[str], None] = "20261107100000_entry_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    if "analyst_settings" not in tables:
        op.create_table(
            "analyst_settings",
            sa.Column("key", sa.String(40), primary_key=True),
            sa.Column("value_json", sa.JSON(), nullable=False),
            sa.Column("updated_by", pk, sa.ForeignKey("app_users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if "rule_check_json" not in {c["name"] for c in insp.get_columns("analyst_entries")}:
        op.add_column("analyst_entries", sa.Column("rule_check_json", sa.JSON(), nullable=True))
    if "tags" not in {c["name"] for c in insp.get_columns("analyst_entry_reviews")}:
        op.add_column("analyst_entry_reviews", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyst_entry_reviews", "tags")
    op.drop_column("analyst_entries", "rule_check_json")
    op.drop_table("analyst_settings")
