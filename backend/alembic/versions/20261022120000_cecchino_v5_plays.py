"""Cecchino V5: tabella delle giocate degli specialisti (solo additiva).

Revision ID: 20261022120000_cecchino_v5_plays
Revises: 20261021090000_v4_clv_estimated
Create Date: 2026-10-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261022120000_cecchino_v5_plays"
down_revision: Union[str, Sequence[str], None] = "20261021090000_v4_clv_estimated"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "cecchino_v5_plays"


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE in sa.inspect(bind).get_table_names():
        return
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        TABLE,
        sa.Column("id", pk, primary_key=True, autoincrement=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("specialist", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("league_code", sa.String(8), nullable=False),
        sa.Column("market_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("expected", sa.Float(), nullable=True),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("prob_prudent", sa.Float(), nullable=False),
        sa.Column("quota", sa.Float(), nullable=False),
        sa.Column("bookmaker_id", sa.Integer(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closing_quota", sa.Float(), nullable=True),
        sa.Column("clv", sa.Float(), nullable=True),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column("profit_units", sa.Float(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day", "specialist", "fixture_id", name="uq_cecchino_v5_plays_day_specialist_fixture"),
    )
    op.create_index("ix_cecchino_v5_plays_day", TABLE, ["day"])
    op.create_index("ix_cecchino_v5_plays_fixture", TABLE, ["fixture_id"])


def downgrade() -> None:
    # Solo additiva: non si cancellano tabelle con dati.
    pass
