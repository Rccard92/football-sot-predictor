"""Diario analisi: progressioni di cassa e giocate degli analisti (solo additiva, tabelle nuove).

Revision ID: 20261030100000_analyst_journal
Revises: 20261029100000_app_users
Create Date: 2026-10-30 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261030100000_analyst_journal"
down_revision: Union[str, Sequence[str], None] = "20261029100000_app_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    if "analyst_cycles" not in tables:
        op.create_table(
            "analyst_cycles",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("user_id", pk, sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("method", sa.String(16), nullable=False),
            sa.Column("settings_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            *_timestamps(),
        )
        op.create_index("ix_analyst_cycles_user_id", "analyst_cycles", ["user_id"])

    if "analyst_entries" not in tables:
        op.create_table(
            "analyst_entries",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("user_id", pk, sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("cycle_id", pk, sa.ForeignKey("analyst_cycles.id"), nullable=True),
            sa.Column("today_fixture_id", pk, nullable=True),
            sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
            sa.Column("match_date", sa.Date(), nullable=False),
            sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
            sa.Column("league_name", sa.String(160), nullable=True),
            sa.Column("country_name", sa.String(80), nullable=True),
            sa.Column("home_team", sa.String(120), nullable=False),
            sa.Column("away_team", sa.String(120), nullable=False),
            sa.Column("source", sa.String(24), nullable=False),
            sa.Column("market_key", sa.String(24), nullable=False),
            sa.Column("market_label", sa.String(40), nullable=False),
            sa.Column("quota", sa.Float(), nullable=False),
            sa.Column("stake", sa.Float(), nullable=True),
            sa.Column("stake_suggested", sa.Float(), nullable=True),
            sa.Column("tool_json", sa.JSON(), nullable=True),
            sa.Column("checklist_json", sa.JSON(), nullable=True),
            sa.Column("analysis_note", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("minutes_spent", sa.Integer(), nullable=True),
            sa.Column("outcome", sa.String(12), nullable=False),
            sa.Column("result_ht", sa.String(12), nullable=True),
            sa.Column("result_ft", sa.String(12), nullable=True),
            sa.Column("profit", sa.Float(), nullable=True),
            sa.Column("profit_units", sa.Float(), nullable=True),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            *_timestamps(),
        )
        for col in ("user_id", "cycle_id", "today_fixture_id", "provider_fixture_id", "match_date"):
            op.create_index(f"ix_analyst_entries_{col}", "analyst_entries", [col])


def downgrade() -> None:
    # Solo additiva: non si cancellano diari ne' progressioni.
    pass
