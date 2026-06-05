"""cecchino_today display fields — score, loghi, match_display_status

Revision ID: 20260614120000
Revises: 20260613120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260614120000"
down_revision: Union[str, Sequence[str], None] = "20260613120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column("cecchino_today_fixtures", sa.Column("country_flag_url", sa.String(length=512), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("league_logo_url", sa.String(length=512), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("home_team_logo_url", sa.String(length=512), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("away_team_logo_url", sa.String(length=512), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("goals_home", sa.Integer(), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("goals_away", sa.Integer(), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("score_fulltime_home", sa.Integer(), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("score_fulltime_away", sa.Integer(), nullable=True))
    op.add_column("cecchino_today_fixtures", sa.Column("elapsed_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "cecchino_today_fixtures",
        sa.Column("match_display_status", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_column("cecchino_today_fixtures", "match_display_status")
    op.drop_column("cecchino_today_fixtures", "elapsed_minutes")
    op.drop_column("cecchino_today_fixtures", "score_fulltime_away")
    op.drop_column("cecchino_today_fixtures", "score_fulltime_home")
    op.drop_column("cecchino_today_fixtures", "goals_away")
    op.drop_column("cecchino_today_fixtures", "goals_home")
    op.drop_column("cecchino_today_fixtures", "away_team_logo_url")
    op.drop_column("cecchino_today_fixtures", "home_team_logo_url")
    op.drop_column("cecchino_today_fixtures", "league_logo_url")
    op.drop_column("cecchino_today_fixtures", "country_flag_url")
