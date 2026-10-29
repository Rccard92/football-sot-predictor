"""Account utenti del tool: utenti, sessioni e storico accessi (solo additiva, tabelle nuove).

Revision ID: 20261029100000_app_users
Revises: 20261024150000_v4_hist_players
Create Date: 2026-10-29 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261029100000_app_users"
down_revision: Union[str, Sequence[str], None] = "20261024150000_v4_hist_players"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    if "app_users" not in tables:
        op.create_table(
            "app_users",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("first_name", sa.String(80), nullable=False),
            sa.Column("last_name", sa.String(80), nullable=False),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("tabs_json", sa.JSON(), nullable=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("must_change_password", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_app_users_email", "app_users", ["email"], unique=True)

    if "app_user_sessions" not in tables:
        op.create_table(
            "app_user_sessions",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("user_id", pk, sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoke_reason", sa.String(32), nullable=True),
            sa.Column("ip", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(300), nullable=True),
            sa.UniqueConstraint("token_hash", name="uq_app_user_sessions_token_hash"),
        )
        op.create_index("ix_app_user_sessions_user_id", "app_user_sessions", ["user_id"])

    if "app_login_events" not in tables:
        op.create_table(
            "app_login_events",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("user_id", pk, sa.ForeignKey("app_users.id"), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("reason", sa.String(32), nullable=True),
            sa.Column("ip", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(300), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_app_login_events_user_id", "app_login_events", ["user_id"])
        op.create_index("ix_app_login_events_created_at", "app_login_events", ["created_at"])


def downgrade() -> None:
    # Solo additiva: non si cancellano utenti ne' storico accessi.
    pass
