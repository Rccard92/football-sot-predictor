"""add_competition_id_columns

Revision ID: 20260604130000
Revises: 20260604120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260604130000"
down_revision: Union[str, Sequence[str], None] = "20260604120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_COMPETITION_ID = [
    "fixtures",
    "player_match_stats",
    "player_season_profiles",
    "player_team_seasons",
    "fixture_team_stats",
    "standings_snapshots",
    "standing_entries",
    "team_sot_predictions",
    "fixture_lineups",
    "fixture_lineup_players",
    "fixture_provider_mappings",
    "fixture_provider_lineups",
    "fixture_missing_players",
    "tracked_betting_picks",
    "referee_season_profiles",
    "odds_discovery_snapshots",
    "sportapi_fixture_odds_snapshots",
    "ingestion_runs",
]

COMPOSITE_INDEXES = [
    ("fixtures", "ix_fixtures_competition_api_fixture", ["competition_id", "api_fixture_id"]),
    ("player_match_stats", "ix_pms_competition_player", ["competition_id", "player_id"]),
    ("player_season_profiles", "ix_psp_competition_season", ["competition_id", "season"]),
    ("tracked_betting_picks", "ix_tbp_competition_fixture", ["competition_id", "fixture_id"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in TABLES_WITH_COMPETITION_ID:
        op.add_column(
            table,
            sa.Column("competition_id", sa.BigInteger(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_competition_id",
            table,
            "competitions",
            ["competition_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_competition_id", table, ["competition_id"])

    for table, index_name, columns in COMPOSITE_INDEXES:
        op.create_index(index_name, table, columns)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, index_name, _columns in reversed(COMPOSITE_INDEXES):
        op.drop_index(index_name, table_name=table)

    for table in reversed(TABLES_WITH_COMPETITION_ID):
        op.drop_index(f"ix_{table}_competition_id", table_name=table)
        op.drop_constraint(f"fk_{table}_competition_id", table, type_="foreignkey")
        op.drop_column(table, "competition_id")
