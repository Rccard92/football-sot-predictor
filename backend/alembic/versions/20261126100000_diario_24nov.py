"""Diario analisi, capitolato di Giovanni del 24/11/2026.

Solo additiva: cinque colonne nuove in analyst_entries (vuote per le giocate di prima) e sette tabelle nuove.
Il downgrade non toglie niente: nessun dato si cancella.

Revision ID: 20261126100000_diario_24nov
Revises: 20261118110000_analyst_extra
Create Date: 2026-11-26 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261126100000_diario_24nov"
down_revision: Union[str, Sequence[str], None] = "20261118110000_analyst_extra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    have = set(insp.get_table_names())
    pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    cols = {c["name"] for c in insp.get_columns("analyst_entries")}
    for name, col in (
        ("is_exception", sa.Boolean()),
        ("exception_reason", sa.Text()),
        ("answers_json", sa.JSON()),
        ("risk_note", sa.Text()),
        ("tech_json", sa.JSON()),
    ):
        if name not in cols:
            op.add_column("analyst_entries", sa.Column(name, col, nullable=True))

    if "analyst_entry_changes" not in have:
        op.create_table(
            "analyst_entry_changes",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("entry_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("user_id", sa.BigInteger(), nullable=True),
            sa.Column("field", sa.String(40), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("after_kickoff", sa.Boolean(), nullable=False, server_default=sa.false()),
            *_ts(),
        )
    if "analyst_entry_photos" not in have:
        op.create_table(
            "analyst_entry_photos",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("entry_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("caption", sa.String(200), nullable=False),
            sa.Column("mime", sa.String(32), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("after_kickoff", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
            *_ts(),
        )
    if "analyst_paper_plays" not in have:
        op.create_table(
            "analyst_paper_plays",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("kind", sa.String(16), nullable=False, index=True),
            sa.Column("user_id", sa.BigInteger(), nullable=True, index=True),
            sa.Column("today_fixture_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
            sa.Column("match_date", sa.Date(), nullable=False, index=True),
            sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
            sa.Column("league_name", sa.String(160), nullable=True),
            sa.Column("home_team", sa.String(120), nullable=False),
            sa.Column("away_team", sa.String(120), nullable=False),
            sa.Column("market_key", sa.String(24), nullable=False),
            sa.Column("market_label", sa.String(40), nullable=False),
            sa.Column("quota", sa.Float(), nullable=True),
            sa.Column("quota_cecchino", sa.Float(), nullable=True),
            sa.Column("reasons_json", sa.JSON(), nullable=True),
            sa.Column("alerts_json", sa.JSON(), nullable=True),
            sa.Column("entry_id", sa.BigInteger(), nullable=True),
            sa.Column("outcome", sa.String(12), nullable=False, server_default="pending"),
            sa.Column("result_ht", sa.String(12), nullable=True),
            sa.Column("result_ft", sa.String(12), nullable=True),
            sa.Column("profit_units", sa.Float(), nullable=True),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            *_ts(),
        )
    if "analyst_venue_geo" not in have:
        op.create_table(
            "analyst_venue_geo",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("city", sa.String(160), nullable=False),
            sa.Column("country", sa.String(80), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("found_name", sa.String(200), nullable=True),
            sa.Column("looked_up_at", sa.DateTime(timezone=True), nullable=False),
            *_ts(),
            sa.UniqueConstraint("city", "country", name="uq_analyst_venue_geo_city_country"),
        )
    if "analyst_weather" not in have:
        op.create_table(
            "analyst_weather",
            sa.Column("fixture_id", sa.BigInteger(), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("hourly_json", sa.JSON(), nullable=True),
            *_ts(),
        )
    if "analyst_league_zones" not in have:
        op.create_table(
            "analyst_league_zones",
            sa.Column("id", pk, primary_key=True, autoincrement=True),
            sa.Column("league_id", sa.BigInteger(), nullable=False),
            sa.Column("season_id", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("teams", sa.Integer(), nullable=True),
            sa.Column("zones_json", sa.JSON(), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            *_ts(),
            sa.UniqueConstraint("league_id", "season_id", name="uq_analyst_league_zones_league_season"),
        )


def downgrade() -> None:
    # niente si cancella (regola del progetto): le colonne e le tabelle restano
    pass
