"""CLV senza margine nel Diario e quota opposta di chiusura nelle giocate V5 (decisioni di Giovanni, 18/11/2026).

- analyst_entries: clv diventa "quota presa x probabilita' di chiusura senza margine - 1"; la vecchia formula
  (quota presa / chiusura - 1) passa nella colonna nuova clv_ratio, con i valori gia' calcolati; closing_prob e'
  la probabilita' di chiusura senza margine. Le giocate gia' salvate hanno clv vuoto finche' il giro del backend
  non rilegge le quote (solo partite degli ultimi 7 giorni, dopo il fornitore non le tiene).
- cecchino_v5_plays: closing_opposite (quota di chiusura dell'esito opposto, stesso book) e clv_novig.

Revision ID: 20261118100000_clv_novig
Revises: 20261109100000_analyst_clv
Create Date: 2026-11-18 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261118100000_clv_novig"
down_revision: Union[str, Sequence[str], None] = "20261109100000_analyst_clv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add(table: str, columns: tuple[tuple[str, sa.types.TypeEngine], ...]) -> list[str]:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    added = []
    for name, kind in columns:
        if name not in have:
            op.add_column(table, sa.Column(name, kind, nullable=True))
            added.append(name)
    return added


def upgrade() -> None:
    added = _add("analyst_entries", (("clv_ratio", sa.Float()), ("closing_prob", sa.Float())))
    if "clv_ratio" in added:
        # i CLV gia' calcolati erano con la vecchia formula: restano nella colonna a parte (niente si perde)
        op.execute("UPDATE analyst_entries SET clv_ratio = clv, clv = NULL WHERE clv IS NOT NULL")
    _add("cecchino_v5_plays", (("closing_opposite", sa.Float()), ("clv_novig", sa.Float())))


def downgrade() -> None:
    # nessuna colonna si cancella (regola: mai perdere dati storici); si rimette solo il vecchio CLV in clv
    op.execute("UPDATE analyst_entries SET clv = clv_ratio WHERE clv_ratio IS NOT NULL")
