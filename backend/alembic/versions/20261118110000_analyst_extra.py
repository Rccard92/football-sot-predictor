"""Diario analisi: seconda lettura quote, calendario con le coppe, formazioni e indisponibili (18/11/2026).

Solo additiva: cinque tabelle nuove, niente cambia in quelle che c'erano.

Revision ID: 20261118110000_analyst_extra
Revises: 20261118100000_clv_novig
Create Date: 2026-11-18 11:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261118110000_analyst_extra"
down_revision: Union[str, Sequence[str], None] = "20261118100000_clv_novig"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    if "analyst_odds_reads" not in have:
        op.create_table(
            "analyst_odds_reads",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("today_fixture_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
            sa.Column("bookmaker_id", sa.Integer(), nullable=False),
            sa.Column("markets_json", sa.JSON(), nullable=True),
            *_ts(),
            sa.UniqueConstraint("today_fixture_id", "kind", name="uq_analyst_odds_reads_fixture_kind"),
        )
    if "analyst_team_games" not in have:
        op.create_table(
            "analyst_team_games",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False),
            sa.Column("day", sa.Date(), nullable=False, index=True),
            sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(16), nullable=True),
            sa.Column("provider_league_id", sa.BigInteger(), nullable=True),
            sa.Column("league_name", sa.String(160), nullable=True),
            sa.Column("league_country", sa.String(80), nullable=True),
            sa.Column("league_round", sa.String(120), nullable=True),
            sa.Column("home_provider_team_id", sa.BigInteger(), nullable=True, index=True),
            sa.Column("away_provider_team_id", sa.BigInteger(), nullable=True, index=True),
            sa.Column("home_team_name", sa.String(160), nullable=True),
            sa.Column("away_team_name", sa.String(160), nullable=True),
            *_ts(),
            sa.UniqueConstraint("provider_fixture_id", name="uq_analyst_team_games_fixture"),
        )
    if "analyst_calendar_days" not in have:
        op.create_table(
            "analyst_calendar_days",
            sa.Column("day", sa.Date(), primary_key=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("games", sa.Integer(), nullable=False),
            *_ts(),
        )
    if "analyst_lineups" not in have:
        op.create_table(
            "analyst_lineups",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("provider_team_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("formation", sa.String(16), nullable=True),
            sa.Column("starters_json", sa.JSON(), nullable=True),
            sa.Column("yellow_cards", sa.Integer(), nullable=True),
            *_ts(),
            sa.UniqueConstraint("provider_fixture_id", "provider_team_id", name="uq_analyst_lineups_fixture_team"),
        )
    if "analyst_injuries" not in have:
        op.create_table(
            "analyst_injuries",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("provider_team_id", sa.BigInteger(), nullable=False),
            sa.Column("player_id", sa.BigInteger(), nullable=False),
            sa.Column("player_name", sa.String(160), nullable=True),
            sa.Column("kind", sa.String(60), nullable=True),
            sa.Column("reason", sa.String(160), nullable=True),
            *_ts(),
            sa.UniqueConstraint("provider_fixture_id", "provider_team_id", "player_id", name="uq_analyst_injuries_fixture_player"),
        )


def downgrade() -> None:
    # regola del progetto: mai cancellare dati storici; le tabelle restano
    pass
