"""Chiave API personale degli account (solo additiva: tre colonne nuove su app_users).

Revision ID: 20261030140000_user_api_keys
Revises: 20261030100000_analyst_journal
Create Date: 2026-10-30 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261030140000_user_api_keys"
down_revision: Union[str, Sequence[str], None] = "20261030100000_analyst_journal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("app_users")}
    if "api_key_hash" not in cols:
        op.add_column("app_users", sa.Column("api_key_hash", sa.String(64), nullable=True))
        op.create_index("ix_app_users_api_key_hash", "app_users", ["api_key_hash"], unique=True)
    if "api_key_created_at" not in cols:
        op.add_column("app_users", sa.Column("api_key_created_at", sa.DateTime(timezone=True), nullable=True))
    if "api_key_last_used_at" not in cols:
        op.add_column("app_users", sa.Column("api_key_last_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_app_users_api_key_hash", table_name="app_users")
    op.drop_column("app_users", "api_key_last_used_at")
    op.drop_column("app_users", "api_key_created_at")
    op.drop_column("app_users", "api_key_hash")
