"""Cecchino V4: prima quota pubblicata delle voci di shortlist (CLV) ed esito piu' largo (solo additiva).

- `published_quota`, `published_bookmaker_id`, `published_at`: la quota vista nella lista provvisoria la prima
  volta che la giocata e' comparsa; resta ferma nei ricalcoli e il CLV si misura da qui contro la chiusura.
  Le voci gia' presenti restano NULL: il loro CLV storico non e' significativo (spesso quota = chiusura -> 0).
- `result` da VARCHAR(8) a VARCHAR(16): `mezza_vinta` / `mezza_persa` (handicap a quarti) sono 11 caratteri.
  Allargare non perde dati; su SQLite la lunghezza non e' applicata e il passo si salta.

Revision ID: 20261020090000_v4_clv_published
Revises: 20261013090000_xg_league_tags
Create Date: 2026-10-20 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261020090000_v4_clv_published"
down_revision: Union[str, Sequence[str], None] = "20261013090000_xg_league_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "cecchino_v4_shortlist_items"


def _columns(bind) -> dict[str, dict]:
    inspector = sa.inspect(bind)
    kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    return {c["name"]: c for c in inspector.get_columns(TABLE, **kw)}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)
    for column in (
        sa.Column("published_quota", sa.Float(), nullable=True),
        sa.Column("published_bookmaker_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    ):
        if column.name not in existing:
            op.add_column(TABLE, column)

    if bind.dialect.name != "sqlite":
        length = getattr(existing.get("result", {}).get("type"), "length", None)
        if length is not None and length < 16:
            op.alter_column(
                TABLE,
                "result",
                existing_type=sa.String(length=8),
                type_=sa.String(length=16),
                existing_nullable=True,
            )


def downgrade() -> None:
    # Migrazione solo additiva: si lasciano colonne e larghezza (togliere le colonne cancellerebbe dati,
    # restringere `result` fallirebbe sulle voci mezza_vinta / mezza_persa).
    pass
