"""step9: fixture_player_stats columns, fixture_lineups coach/start_xi, player_sot_profiles, player_availability_events

Revision ID: 20260510120000
Revises: 20260509120000
Create Date: 2026-05-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260510120000"
down_revision: Union[str, Sequence[str], None] = "20260509120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector: sa.Inspector, bind) -> set[str]:
    if bind.dialect.name == "postgresql":
        return set(inspector.get_table_names(schema="public"))
    return set(inspector.get_table_names())


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in _table_names(inspector, bind)


def column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in _table_names(inspector, bind):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if table_exists("fixture_player_stats"):
        cols = [
            ("position", sa.String(32), True),
            ("rating", sa.Float(), True),
            ("captain", sa.Boolean(), True),
            ("substitute", sa.Boolean(), True),
            ("shots_total", sa.Integer(), True),
            ("shots_on_target", sa.Integer(), True),
            ("goals", sa.Integer(), True),
            ("assists", sa.Integer(), True),
            ("passes_total", sa.Integer(), True),
            ("passes_key", sa.Integer(), True),
            ("passes_accuracy_pct", sa.Float(), True),
            ("tackles_total", sa.Integer(), True),
            ("tackles_blocks", sa.Integer(), True),
            ("interceptions", sa.Integer(), True),
            ("duels_total", sa.Integer(), True),
            ("duels_won", sa.Integer(), True),
            ("dribbles_attempts", sa.Integer(), True),
            ("dribbles_success", sa.Integer(), True),
            ("fouls_drawn", sa.Integer(), True),
            ("fouls_committed", sa.Integer(), True),
            ("yellow_cards", sa.Integer(), True),
            ("red_cards", sa.Integer(), True),
        ]
        for name, typ, nullable in cols:
            if not column_exists("fixture_player_stats", name):
                op.add_column(
                    "fixture_player_stats",
                    sa.Column(name, typ, nullable=nullable),
                )

    if table_exists("fixture_lineups"):
        if not column_exists("fixture_lineups", "coach_name"):
            op.add_column("fixture_lineups", sa.Column("coach_name", sa.String(255), nullable=True))
        if not column_exists("fixture_lineups", "start_xi"):
            op.add_column(
                "fixture_lineups",
                sa.Column("start_xi", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )
        if not column_exists("fixture_lineups", "substitutes"):
            op.add_column(
                "fixture_lineups",
                sa.Column("substitutes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )

    if not table_exists("player_sot_profiles"):
        op.create_table(
            "player_sot_profiles",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("season_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("player_id", sa.BigInteger(), nullable=False),
            sa.Column("appearances", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("starts", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("total_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("avg_minutes", sa.Float(), nullable=True),
            sa.Column("total_shots", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("total_shots_on_target", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("shots_on_target_per90", sa.Float(), nullable=True),
            sa.Column("team_sot_share_pct", sa.Float(), nullable=True),
            sa.Column("last5_shots_on_target_per90", sa.Float(), nullable=True),
            sa.Column("reliability_score", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("impact_score", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("season_id", "player_id", name="uq_player_sot_profiles_season_player"),
        )
        op.create_index(
            op.f("ix_player_sot_profiles_season_id"),
            "player_sot_profiles",
            ["season_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_player_sot_profiles_team_id"),
            "player_sot_profiles",
            ["team_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_player_sot_profiles_player_id"),
            "player_sot_profiles",
            ["player_id"],
            unique=False,
        )

    if not table_exists("player_availability_events"):
        op.create_table(
            "player_availability_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("season_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=True),
            sa.Column("player_id", sa.BigInteger(), nullable=True),
            sa.Column("api_player_id", sa.BigInteger(), nullable=True),
            sa.Column("player_name", sa.String(255), nullable=False),
            sa.Column("fixture_id", sa.BigInteger(), nullable=True),
            sa.Column("type", sa.String(64), nullable=False),
            sa.Column("reason", sa.String(512), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_player_availability_events_season_id"),
            "player_availability_events",
            ["season_id"],
            unique=False,
        )


def downgrade() -> None:
    if table_exists("player_availability_events"):
        op.drop_index(op.f("ix_player_availability_events_season_id"), table_name="player_availability_events")
        op.drop_table("player_availability_events")

    if table_exists("player_sot_profiles"):
        op.drop_index(op.f("ix_player_sot_profiles_player_id"), table_name="player_sot_profiles")
        op.drop_index(op.f("ix_player_sot_profiles_team_id"), table_name="player_sot_profiles")
        op.drop_index(op.f("ix_player_sot_profiles_season_id"), table_name="player_sot_profiles")
        op.drop_table("player_sot_profiles")

    if table_exists("fixture_lineups"):
        for col in ("substitutes", "start_xi", "coach_name"):
            if column_exists("fixture_lineups", col):
                op.drop_column("fixture_lineups", col)

    if table_exists("fixture_player_stats"):
        for col in (
            "red_cards",
            "yellow_cards",
            "fouls_committed",
            "fouls_drawn",
            "dribbles_success",
            "dribbles_attempts",
            "duels_won",
            "duels_total",
            "interceptions",
            "tackles_blocks",
            "tackles_total",
            "passes_accuracy_pct",
            "passes_key",
            "passes_total",
            "assists",
            "goals",
            "shots_on_target",
            "shots_total",
            "substitute",
            "captain",
            "rating",
            "position",
        ):
            if column_exists("fixture_player_stats", col):
                op.drop_column("fixture_player_stats", col)
