"""create_player_db_tables: Player DB UUID (registry, team-season, match stats, season profiles)

Sostituisce le tabelle legacy bigserial `player_registry` / `player_team_seasons` (20260516120000)
con lo schema UUID richiesto; aggiunge `player_match_stats` e `player_season_profiles`.

Revision ID: 20260517120000
Revises: 20260516120000

Downgrade: rimuove solo le quattro tabelle create qui; non ripristina lo schema legacy.

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260517120000"
down_revision: Union[str, Sequence[str], None] = "20260516120000"
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


def column_exists(table: str, col: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in _table_names(inspector, bind):
        return False
    col_kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    return col in {c["name"] for c in inspector.get_columns(table, **col_kw)}


def index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in _table_names(inspector, bind):
        return False
    kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    return any(ix.get("name") == name for ix in inspector.get_indexes(table, **kw))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    json_t = postgresql.JSONB(astext_type=sa.Text())
    uuid_t = postgresql.UUID(as_uuid=True)

    # --- teardown legacy Player DB (bigserial + players.registry_id) ---
    if table_exists("players") and column_exists("players", "registry_id"):
        op.execute(sa.text("ALTER TABLE players DROP CONSTRAINT IF EXISTS fk_players_player_registry"))
        if index_exists("players", op.f("ix_players_registry_id")):
            op.drop_index(op.f("ix_players_registry_id"), table_name="players")
        op.drop_column("players", "registry_id")

    if table_exists("player_team_seasons"):
        op.drop_table("player_team_seasons")

    if table_exists("player_registry"):
        op.drop_table("player_registry")

    # --- player_registry (UUID) ---
    op.create_table(
        "player_registry",
        sa.Column(
            "id",
            uuid_t,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("api_player_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_player_id", name="uq_player_registry_api_player_id"),
    )
    op.create_index("ix_player_registry_api_player_id", "player_registry", ["api_player_id"], unique=False)
    op.create_index("ix_player_registry_normalized_name", "player_registry", ["normalized_name"], unique=False)

    # --- player_team_seasons ---
    op.create_table(
        "player_team_seasons",
        sa.Column("id", uuid_t, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("api_team_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", uuid_t, nullable=False),
        sa.Column("api_player_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player_id"], ["player_registry.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "season",
            "league_id",
            "api_team_id",
            "api_player_id",
            name="uq_player_team_seasons_season_league_api_team_player",
        ),
    )
    op.create_index(
        "ix_player_team_seasons_season_league_api_team",
        "player_team_seasons",
        ["season", "league_id", "api_team_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_team_seasons_api_player_id",
        "player_team_seasons",
        ["api_player_id"],
        unique=False,
    )
    op.create_index("ix_player_team_seasons_team_id", "player_team_seasons", ["team_id"], unique=False)
    op.create_index("ix_player_team_seasons_player_id", "player_team_seasons", ["player_id"], unique=False)

    # --- player_match_stats ---
    op.create_table(
        "player_match_stats",
        sa.Column("id", uuid_t, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("api_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("api_team_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", uuid_t, nullable=False),
        sa.Column("api_player_id", sa.BigInteger(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("position", sa.String(length=255), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("substitute", sa.Boolean(), nullable=True),
        sa.Column("shots_total", sa.Integer(), nullable=True),
        sa.Column("shots_on", sa.Integer(), nullable=True),
        sa.Column("goals_total", sa.Integer(), nullable=True),
        sa.Column("goals_assists", sa.Integer(), nullable=True),
        sa.Column("passes_total", sa.Integer(), nullable=True),
        sa.Column("passes_key", sa.Integer(), nullable=True),
        sa.Column("passes_accuracy", sa.Float(), nullable=True),
        sa.Column("dribbles_attempts", sa.Integer(), nullable=True),
        sa.Column("dribbles_success", sa.Integer(), nullable=True),
        sa.Column("fouls_drawn", sa.Integer(), nullable=True),
        sa.Column("fouls_committed", sa.Integer(), nullable=True),
        sa.Column("cards_yellow", sa.Integer(), nullable=True),
        sa.Column("cards_red", sa.Integer(), nullable=True),
        sa.Column("penalty_scored", sa.Integer(), nullable=True),
        sa.Column("penalty_missed", sa.Integer(), nullable=True),
        sa.Column("penalty_won", sa.Integer(), nullable=True),
        sa.Column("raw_json", json_t, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player_id"], ["player_registry.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fixture_id",
            "api_team_id",
            "api_player_id",
            name="uq_player_match_stats_fixture_api_team_player",
        ),
    )
    op.create_index("ix_player_match_stats_fixture_id", "player_match_stats", ["fixture_id"], unique=False)
    op.create_index(
        "ix_player_match_stats_api_fixture_id",
        "player_match_stats",
        ["api_fixture_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_match_stats_season_league_api_team",
        "player_match_stats",
        ["season", "league_id", "api_team_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_match_stats_api_player_id",
        "player_match_stats",
        ["api_player_id"],
        unique=False,
    )
    op.create_index("ix_player_match_stats_player_id", "player_match_stats", ["player_id"], unique=False)

    # --- player_season_profiles ---
    op.create_table(
        "player_season_profiles",
        sa.Column("id", uuid_t, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("api_team_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", uuid_t, nullable=False),
        sa.Column("api_player_id", sa.BigInteger(), nullable=False),
        sa.Column("matches_played", sa.Integer(), nullable=True),
        sa.Column("minutes_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("minutes_avg", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("starts_estimated", sa.Integer(), nullable=True),
        sa.Column("shots_total", sa.Integer(), nullable=True),
        sa.Column("shots_on", sa.Integer(), nullable=True),
        sa.Column("shots_total_per90", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("shots_on_per90", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("shot_accuracy", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("goals_total", sa.Integer(), nullable=True),
        sa.Column("assists_total", sa.Integer(), nullable=True),
        sa.Column("key_passes_total", sa.Integer(), nullable=True),
        sa.Column("key_passes_per90", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("recent_minutes_last5", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("recent_shots_total_last5", sa.Integer(), nullable=True),
        sa.Column("recent_shots_on_last5", sa.Integer(), nullable=True),
        sa.Column("recent_rating_last5", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("avg_rating", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("team_shots_share", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("team_sot_share", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("shooting_impact_score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("reliability_score", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player_id"], ["player_registry.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "season",
            "league_id",
            "api_team_id",
            "api_player_id",
            name="uq_player_season_profiles_season_league_api_team_player",
        ),
    )
    op.create_index(
        "ix_player_season_profiles_season_league_api_team",
        "player_season_profiles",
        ["season", "league_id", "api_team_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_season_profiles_api_player_id",
        "player_season_profiles",
        ["api_player_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_season_profiles_player_id",
        "player_season_profiles",
        ["player_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for tbl in (
        "player_season_profiles",
        "player_match_stats",
        "player_team_seasons",
        "player_registry",
    ):
        if table_exists(tbl):
            op.drop_table(tbl)
