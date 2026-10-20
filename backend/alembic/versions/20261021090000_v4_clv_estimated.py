"""Cecchino V4: CLV stimato dalle istantanee del registro quote (solo additiva).

- `first_snapshot_quota`, `first_snapshot_at`: prima quota salvata nel giorno della partita, stesso book del prezzo
  di riferimento, prima del calcio d'inizio.
- `clv_estimated`: first_snapshot_quota / closing_quota - 1. Vale anche per le voci create prima del 20/10/2026,
  il cui `clv` e' 0 per costruzione (quota della voce = chiusura). Le colonne esistenti non si toccano.

Revision ID: 20261021090000_v4_clv_estimated
Revises: 20261020090000_v4_clv_published
Create Date: 2026-10-21 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261021090000_v4_clv_estimated"
down_revision: Union[str, Sequence[str], None] = "20261020090000_v4_clv_published"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "cecchino_v4_shortlist_items"


def _columns(bind) -> set[str]:
    inspector = sa.inspect(bind)
    kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    return {c["name"] for c in inspector.get_columns(TABLE, **kw)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    for column in (
        sa.Column("first_snapshot_quota", sa.Float(), nullable=True),
        sa.Column("first_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clv_estimated", sa.Float(), nullable=True),
    ):
        if column.name not in existing:
            op.add_column(TABLE, column)


def downgrade() -> None:
    # Migrazione solo additiva: togliere le colonne cancellerebbe dati.
    pass
