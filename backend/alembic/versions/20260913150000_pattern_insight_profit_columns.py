"""pattern insight: profitto e giocate con quota salvati per scoperta e verifiche

Servono per sommare ROI e profitto su tutte le stagioni senza stime.

Revision ID: 20260913150000_pi_profit
Revises: 20260913120000_pi_odds_tiers
Create Date: 2026-09-13 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260913150000_pi_profit"
down_revision: Union[str, Sequence[str], None] = "20260913120000_pi_odds_tiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cecchino_run_v2_pattern_insight_candidates",
        sa.Column("profit_units", sa.Numeric(10, 3), nullable=True),
    )
    op.add_column(
        "cecchino_run_v2_pattern_insight_candidates",
        sa.Column("n_priced", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cecchino_run_v2_pattern_validations",
        sa.Column("n_priced", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cecchino_run_v2_pattern_validations", "n_priced")
    op.drop_column("cecchino_run_v2_pattern_insight_candidates", "n_priced")
    op.drop_column("cecchino_run_v2_pattern_insight_candidates", "profit_units")
