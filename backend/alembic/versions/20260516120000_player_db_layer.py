"""Player DB: registry, rose per stagione, colonne fps/profili (api_player_id, rigori, aggregati estesi).

Revision ID: 20260516120000
Revises: 20260515120000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260516120000"
down_revision: Union[str, Sequence[str], None] = "20260515120000"
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


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in _table_names(inspector, bind):
        return False
    col_kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    columns = [col["name"] for col in inspector.get_columns(table_name, **col_kw)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in _table_names(inspector, bind):
        return False
    kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    for ix in inspector.get_indexes(table_name, **kw):
        if ix.get("name") == index_name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    json_t = postgresql.JSONB(astext_type=sa.Text())

    if not table_exists("player_registry"):
        op.create_table(
            "player_registry",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("api_player_id", sa.BigInteger(), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("name_normalized", sa.String(length=255), nullable=False),
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("api_player_id", name="uq_player_registry_api_player_id"),
        )
        op.create_index(
            op.f("ix_player_registry_api_player_id"),
            "player_registry",
            ["api_player_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_player_registry_name_normalized"),
            "player_registry",
            ["name_normalized"],
            unique=False,
        )

    if not table_exists("player_team_seasons"):
        op.create_table(
            "player_team_seasons",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("season_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("player_registry_id", sa.BigInteger(), nullable=False),
            sa.Column("jersey_number", sa.Integer(), nullable=True),
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
            sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["player_registry_id"],
                ["player_registry.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "season_id",
                "team_id",
                "player_registry_id",
                name="uq_player_team_seasons_season_team_registry",
            ),
        )
        op.create_index(
            op.f("ix_player_team_seasons_season_id"),
            "player_team_seasons",
            ["season_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_player_team_seasons_team_id"),
            "player_team_seasons",
            ["team_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_player_team_seasons_player_registry_id"),
            "player_team_seasons",
            ["player_registry_id"],
            unique=False,
        )

    if table_exists("players") and not column_exists("players", "registry_id"):
        op.add_column("players", sa.Column("registry_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            "fk_players_player_registry",
            "players",
            "player_registry",
            ["registry_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(op.f("ix_players_registry_id"), "players", ["registry_id"], unique=False)

    if table_exists("fixture_player_stats"):
        for col_name, col_type, nullable in (
            ("api_player_id", sa.BigInteger(), True),
            ("penalty_scored", sa.Integer(), True),
            ("penalty_missed", sa.Integer(), True),
            ("penalty_won", sa.Integer(), True),
        ):
            if not column_exists("fixture_player_stats", col_name):
                op.add_column(
                    "fixture_player_stats",
                    sa.Column(col_name, col_type, nullable=nullable),
                )

        if column_exists("fixture_player_stats", "api_player_id"):
            if bind.dialect.name == "postgresql":
                op.execute(
                    sa.text(
                        """
                        UPDATE fixture_player_stats fps
                        SET api_player_id = p.api_player_id
                        FROM players p
                        WHERE p.id = fps.player_id
                          AND fps.api_player_id IS NULL;
                        """,
                    ),
                )
            else:
                op.execute(
                    sa.text(
                        """
                        UPDATE fixture_player_stats
                        SET api_player_id = (
                            SELECT api_player_id FROM players
                            WHERE players.id = fixture_player_stats.player_id
                        )
                        WHERE api_player_id IS NULL;
                        """,
                    ),
                )

        if not index_exists("fixture_player_stats", "ix_fixture_player_stats_api_player_id"):
            op.create_index(
                "ix_fixture_player_stats_api_player_id",
                "fixture_player_stats",
                ["api_player_id"],
                unique=False,
            )
        if not index_exists("fixture_player_stats", "ix_fixture_player_stats_fixture_team_api"):
            op.create_index(
                "ix_fixture_player_stats_fixture_team_api",
                "fixture_player_stats",
                ["fixture_id", "team_id", "api_player_id"],
                unique=False,
            )

    if table_exists("player_sot_profiles"):
        profile_cols = [
            ("goals_total", sa.Integer(), False, sa.text("0")),
            ("assists_total", sa.Integer(), False, sa.text("0")),
            ("key_passes_total", sa.Integer(), False, sa.text("0")),
            ("key_passes_per90", sa.Float(), True, None),
            ("avg_rating", sa.Float(), True, None),
            ("recent_minutes_last5", sa.Integer(), True, None),
            ("recent_shots_total_last5", sa.Integer(), True, None),
            ("recent_shots_on_last5", sa.Integer(), True, None),
            ("recent_rating_last5", sa.Float(), True, None),
            ("team_total_shots_share_pct", sa.Float(), True, None),
        ]
        for name, typ, null, default in profile_cols:
            if not column_exists("player_sot_profiles", name):
                kwargs: dict = {"nullable": null}
                if default is not None:
                    kwargs["server_default"] = default
                op.add_column("player_sot_profiles", sa.Column(name, typ, **kwargs))


def downgrade() -> None:
    if table_exists("player_sot_profiles"):
        for col in (
            "team_total_shots_share_pct",
            "recent_rating_last5",
            "recent_shots_on_last5",
            "recent_shots_total_last5",
            "recent_minutes_last5",
            "avg_rating",
            "key_passes_per90",
            "key_passes_total",
            "assists_total",
            "goals_total",
        ):
            if column_exists("player_sot_profiles", col):
                op.drop_column("player_sot_profiles", col)

    if table_exists("fixture_player_stats"):
        if index_exists("fixture_player_stats", "ix_fixture_player_stats_fixture_team_api"):
            op.drop_index("ix_fixture_player_stats_fixture_team_api", table_name="fixture_player_stats")
        if index_exists("fixture_player_stats", "ix_fixture_player_stats_api_player_id"):
            op.drop_index("ix_fixture_player_stats_api_player_id", table_name="fixture_player_stats")
        for col in ("penalty_won", "penalty_missed", "penalty_scored", "api_player_id"):
            if column_exists("fixture_player_stats", col):
                op.drop_column("fixture_player_stats", col)

    if table_exists("players") and column_exists("players", "registry_id"):
        op.drop_index(op.f("ix_players_registry_id"), table_name="players")
        op.drop_constraint("fk_players_player_registry", "players", type_="foreignkey")
        op.drop_column("players", "registry_id")

    if table_exists("player_team_seasons"):
        op.drop_index(op.f("ix_player_team_seasons_player_registry_id"), table_name="player_team_seasons")
        op.drop_index(op.f("ix_player_team_seasons_team_id"), table_name="player_team_seasons")
        op.drop_index(op.f("ix_player_team_seasons_season_id"), table_name="player_team_seasons")
        op.drop_table("player_team_seasons")

    if table_exists("player_registry"):
        op.drop_index(op.f("ix_player_registry_name_normalized"), table_name="player_registry")
        op.drop_index(op.f("ix_player_registry_api_player_id"), table_name="player_registry")
        op.drop_table("player_registry")
