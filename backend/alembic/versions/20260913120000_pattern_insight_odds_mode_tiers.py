"""pattern insight: modalita' quote, versione motore e statistiche per divisione

Revision ID: 20260913120000_pi_odds_tiers
Revises: 20260913090000_pval_tables
Create Date: 2026-09-13 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260913120000_pi_odds_tiers"
down_revision: Union[str, Sequence[str], None] = "20260913090000_pval_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Le analisi gia' esistenti sono state fatte con le quote come salvate da
    # Run V2 e col motore Python: i default del backfill lo riflettono.
    op.add_column(
        "cecchino_run_v2_pattern_insight_runs",
        sa.Column("odds_mode", sa.String(16), nullable=False, server_default="v2"),
    )
    op.add_column(
        "cecchino_run_v2_pattern_insight_runs",
        sa.Column("engine_version", sa.String(32), nullable=False, server_default="python_v1"),
    )
    op.add_column(
        "cecchino_run_v2_pattern_validations",
        sa.Column("tier_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cecchino_run_v2_pattern_validations", "tier_json")
    op.drop_column("cecchino_run_v2_pattern_insight_runs", "engine_version")
    op.drop_column("cecchino_run_v2_pattern_insight_runs", "odds_mode")
