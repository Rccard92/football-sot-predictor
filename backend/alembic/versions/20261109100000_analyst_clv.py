"""Diario analisi: quota presa con il bookmaker, quota del tool a parte, quota di chiusura e CLV.

Solo additiva: colonne nuove, tutte nullable (le giocate gia' salvate restano come sono).

Revision ID: 20261109100000_analyst_clv
Revises: 20261107140000_analyst_rules
Create Date: 2026-11-09 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261109100000_analyst_clv"
down_revision: Union[str, Sequence[str], None] = "20261107140000_analyst_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("bookmaker", sa.String(40)),
    ("quota_tool", sa.Float()),
    ("quota_tool_at", sa.DateTime(timezone=True)),
    ("closing_quota", sa.Float()),
    ("closing_bookmaker", sa.String(40)),
    ("closing_at", sa.DateTime(timezone=True)),
    ("closing_status", sa.String(16)),
    ("closing_note", sa.String(120)),
    ("clv", sa.Float()),
)


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("analyst_entries")}
    for name, kind in _COLUMNS:
        if name not in have:
            op.add_column("analyst_entries", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _kind in reversed(_COLUMNS):
        op.drop_column("analyst_entries", name)
