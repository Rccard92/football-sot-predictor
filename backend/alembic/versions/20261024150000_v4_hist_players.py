"""Cecchino V4: storico giocatori e assenze; V5: giocate delle combo (solo additiva).

Revision ID: 20261024150000_v4_hist_players
Revises: 20261022120000_cecchino_v5_plays
Create Date: 2026-10-24 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024150000_v4_hist_players"
down_revision: Union[str, Sequence[str], None] = "20261022120000_cecchino_v5_plays"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("cecchino_v4_fixtures")}
    if "players_fetched_at" not in cols:
        op.add_column("cecchino_v4_fixtures", sa.Column("players_fetched_at", sa.DateTime(timezone=True), nullable=True))
    if "cecchino_v4_injuries" not in insp.get_table_names():
        pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
        op.create_table(
            "cecchino_v4_injuries",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("league_code", sa.String(8), nullable=False),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("fixture_api_id", sa.BigInteger(), nullable=False),
            sa.Column("team_api_id", sa.BigInteger(), nullable=True),
            sa.Column("player_api_id", sa.BigInteger(), nullable=False),
            sa.Column("player_name", sa.String(128), nullable=True),
            sa.Column("kind", sa.String(32), nullable=True),
            sa.Column("reason", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("fixture_api_id", "player_api_id", name="uq_cecchino_v4_injuries_fixture_player"),
        )
        op.create_index("ix_cecchino_v4_injuries_league_season", "cecchino_v4_injuries", ["league_code", "season"])
    v5_cols = {c["name"] for c in insp.get_columns("cecchino_v5_plays")}
    if "legs_json" not in v5_cols:
        op.add_column("cecchino_v5_plays", sa.Column("legs_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Solo additiva: non si cancellano dati.
    pass
