"""fixture_lineup_players + colonne fixture_lineups + backfill da JSONB

Revision ID: 20260518120000
Revises: 20260517120000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260518120000"
down_revision: Union[str, Sequence[str], None] = "20260517120000"
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


def _parse_player_entry(entry: Any, *, is_starter: bool) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    pl = entry.get("player")
    if not isinstance(pl, dict) or not pl.get("name"):
        return None
    api_id = pl.get("id")
    try:
        api_player_id = int(api_id) if api_id is not None else None
    except (TypeError, ValueError):
        api_player_id = None
    num = pl.get("number")
    try:
        number = int(num) if num is not None else None
    except (TypeError, ValueError):
        number = None
    pos = pl.get("pos")
    grid = pl.get("grid")
    return {
        "api_player_id": api_player_id,
        "player_name": str(pl.get("name"))[:255],
        "number": number,
        "position": str(pos)[:16] if pos is not None else None,
        "grid": str(grid)[:16] if grid is not None else None,
        "is_starter": is_starter,
        "is_substitute": not is_starter,
    }


def _players_from_jsonb(start_xi: Any, substitutes: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(start_xi, list):
        for e in start_xi:
            row = _parse_player_entry(e, is_starter=True)
            if row:
                out.append(row)
    if isinstance(substitutes, list):
        for e in substitutes:
            row = _parse_player_entry(e, is_starter=False)
            if row:
                out.append(row)
    return out


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    uuid_t = postgresql.UUID(as_uuid=True)
    json_t = postgresql.JSONB(astext_type=sa.Text())

    if table_exists("fixture_lineups"):
        for col, coltype in (
            ("api_fixture_id", sa.BigInteger()),
            ("season", sa.Integer()),
            ("league_id", sa.BigInteger()),
            ("api_team_id", sa.BigInteger()),
            ("is_available", sa.Boolean()),
            ("is_official", sa.Boolean()),
            ("source", sa.Text()),
            ("fetched_at", sa.DateTime(timezone=True)),
        ):
            if not column_exists("fixture_lineups", col):
                kwargs: dict = {"nullable": True}
                if col == "is_available":
                    kwargs = {"nullable": False, "server_default": sa.text("false")}
                elif col == "source":
                    kwargs = {"nullable": False, "server_default": sa.text("'api_football_fixtures_lineups'")}
                op.add_column("fixture_lineups", sa.Column(col, coltype, **kwargs))

        op.execute(
            sa.text(
                """
                UPDATE fixture_lineups fl
                SET api_fixture_id = f.api_fixture_id,
                    league_id = f.league_id,
                    season = s.year,
                    api_team_id = t.api_team_id
                FROM fixtures f
                JOIN seasons s ON s.id = f.season_id
                JOIN teams t ON t.id = fl.team_id
                WHERE fl.fixture_id = f.id
                  AND fl.api_fixture_id IS NULL
                """
            ),
        )

    if not table_exists("fixture_lineup_players"):
        op.create_table(
            "fixture_lineup_players",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("fixture_lineup_id", sa.BigInteger(), nullable=False),
            sa.Column("fixture_id", sa.BigInteger(), nullable=False),
            sa.Column("api_fixture_id", sa.BigInteger(), nullable=False),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("league_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("api_team_id", sa.BigInteger(), nullable=False),
            sa.Column("player_id", uuid_t, nullable=True),
            sa.Column("api_player_id", sa.BigInteger(), nullable=True),
            sa.Column("player_name", sa.String(255), nullable=False),
            sa.Column("number", sa.Integer(), nullable=True),
            sa.Column("position", sa.String(16), nullable=True),
            sa.Column("grid", sa.String(16), nullable=True),
            sa.Column("is_starter", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_substitute", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["fixture_lineup_id"], ["fixture_lineups.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["player_id"], ["player_registry.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "fixture_lineup_id",
                "api_player_id",
                "is_starter",
                name="uq_fixture_lineup_players_lineup_player_starter",
            ),
        )
        op.create_index("ix_fixture_lineup_players_fixture_lineup_id", "fixture_lineup_players", ["fixture_lineup_id"])
        op.create_index("ix_fixture_lineup_players_fixture_id", "fixture_lineup_players", ["fixture_id"])
        op.create_index("ix_fixture_lineup_players_api_fixture_id", "fixture_lineup_players", ["api_fixture_id"])

    # Backfill normalized players from existing JSONB
    if table_exists("fixture_lineups") and table_exists("fixture_lineup_players"):
        rows = bind.execute(
            sa.text(
                """
                SELECT fl.id, fl.fixture_id, fl.api_fixture_id, fl.season, fl.league_id,
                       fl.team_id, fl.api_team_id, fl.start_xi, fl.substitutes, fl.updated_at
                FROM fixture_lineups fl
                WHERE (fl.start_xi IS NOT NULL OR fl.substitutes IS NOT NULL)
                  AND NOT EXISTS (
                    SELECT 1 FROM fixture_lineup_players flp WHERE flp.fixture_lineup_id = fl.id LIMIT 1
                  )
                """
            ),
        ).fetchall()

        for row in rows:
            fl_id, fx_id, api_fx, season, league_id, team_id, api_team, start_xi, subs, updated_at = row
            if api_fx is None or season is None or league_id is None or api_team is None:
                continue
            sx = start_xi
            su = subs
            if isinstance(sx, str):
                sx = json.loads(sx)
            if isinstance(su, str):
                su = json.loads(su)
            players = _players_from_jsonb(sx, su)
            if not players:
                continue
            bind.execute(
                sa.text("UPDATE fixture_lineups SET is_available = true, fetched_at = :fa WHERE id = :id"),
                {"fa": updated_at, "id": fl_id},
            )
            for p in players:
                reg = None
                if p["api_player_id"] is not None:
                    reg = bind.execute(
                        sa.text("SELECT id FROM player_registry WHERE api_player_id = :apid LIMIT 1"),
                        {"apid": p["api_player_id"]},
                    ).scalar()
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO fixture_lineup_players (
                            fixture_lineup_id, fixture_id, api_fixture_id, season, league_id,
                            team_id, api_team_id, player_id, api_player_id, player_name,
                            number, position, grid, is_starter, is_substitute
                        ) VALUES (
                            :fl_id, :fx_id, :api_fx, :season, :league_id,
                            :team_id, :api_team, :player_id, :api_player_id, :player_name,
                            :number, :position, :grid, :is_starter, :is_substitute
                        )
                        ON CONFLICT ON CONSTRAINT uq_fixture_lineup_players_lineup_player_starter DO NOTHING
                        """
                    ),
                    {
                        "fl_id": fl_id,
                        "fx_id": fx_id,
                        "api_fx": api_fx,
                        "season": season,
                        "league_id": league_id,
                        "team_id": team_id,
                        "api_team": api_team,
                        "player_id": reg,
                        "api_player_id": p["api_player_id"],
                        "player_name": p["player_name"],
                        "number": p["number"],
                        "position": p["position"],
                        "grid": p["grid"],
                        "is_starter": p["is_starter"],
                        "is_substitute": p["is_substitute"],
                    },
                )


def downgrade() -> None:
    if table_exists("fixture_lineup_players"):
        op.drop_table("fixture_lineup_players")
    if table_exists("fixture_lineups"):
        for col in (
            "fetched_at",
            "source",
            "is_official",
            "is_available",
            "api_team_id",
            "league_id",
            "season",
            "api_fixture_id",
        ):
            if column_exists("fixture_lineups", col):
                op.drop_column("fixture_lineups", col)
