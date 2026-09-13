"""cecchino v3: indice per confrontare le previsioni di due calcoli

Revision ID: 20260914140000_v3_lookup_idx
Revises: 20260914120000_v3_specialists
Create Date: 2026-09-14 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260914140000_v3_lookup_idx"
down_revision: Union[str, Sequence[str], None] = "20260914120000_v3_specialists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_cecchino_v3_market_pred_run_lab_market",
        "cecchino_v3_market_predictions",
        ["run_id", "lab_match_id", "market_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_cecchino_v3_market_pred_run_lab_market", table_name="cecchino_v3_market_predictions")
