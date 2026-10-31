"""V5: riapre le giocate regolate con il punteggio del momento, per ricalcolarle a partita finita.

Fino al 31/10/2026 la V5 chiudeva le giocate appena ft_home/ft_away erano pieni, ma durante la partita
contengono i gol del momento. Valore, specialisti di campionato e combo si regolano sul punteggio, quindi
erano quasi tutti chiusi a partita in corso; angoli, cartellini e tiri in porta aspettano le statistiche
di fine partita e restano come sono.
I vecchi esiti si salvano in cecchino_v5_play_corrections (niente va perso, il downgrade li rimette);
le giocate riaperte le richiude il passo "v5" dei job con la regola corretta (solo FT/AET/PEN).

Revision ID: 20261031090000_v5_resettle
Revises: 20261030140000_user_api_keys
Create Date: 2026-10-31 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261031090000_v5_resettle"
down_revision: Union[str, Sequence[str], None] = "20261030140000_user_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REASON = "regolata a partita in corso, riaperta il 31/10/2026"
_WHERE = (
    "specialist NOT IN ('angoli', 'cartellini', 'tiri_porta') "
    "AND settled_at IS NOT NULL AND result IN ('vinta', 'persa')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if "cecchino_v5_play_corrections" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "cecchino_v5_play_corrections",
            sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("play_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("specialist", sa.String(24), nullable=False),
            sa.Column("market_key", sa.String(64), nullable=False),
            sa.Column("old_result", sa.String(16), nullable=True),
            sa.Column("old_profit_units", sa.Float(), nullable=True),
            sa.Column("old_settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reason", sa.String(160), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    bind.execute(
        sa.text(
            "INSERT INTO cecchino_v5_play_corrections "
            "(play_id, specialist, market_key, old_result, old_profit_units, old_settled_at, reason) "
            f"SELECT id, specialist, market_key, result, profit_units, settled_at, :reason FROM cecchino_v5_plays WHERE {_WHERE}"
        ),
        {"reason": _REASON},
    )
    bind.execute(sa.text(f"UPDATE cecchino_v5_plays SET result = NULL, profit_units = NULL, settled_at = NULL WHERE {_WHERE}"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE cecchino_v5_plays SET result = c.old_result, profit_units = c.old_profit_units, "
            "settled_at = c.old_settled_at FROM cecchino_v5_play_corrections c "
            "WHERE c.play_id = cecchino_v5_plays.id AND c.reason = :reason"
        ),
        {"reason": _REASON},
    )
