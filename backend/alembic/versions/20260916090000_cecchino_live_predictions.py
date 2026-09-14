"""registro previsioni live per motore (V2, V2.5, V3)

Revision ID: 20260916090000_live_predictions
Revises: 20260915090000_master_patterns
Create Date: 2026-09-16 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260916090000_live_predictions"
down_revision: Union[str, Sequence[str], None] = "20260915090000_master_patterns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_live_predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("today_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("local_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("country_name", sa.String(128), nullable=True),
        sa.Column("league_name", sa.String(255), nullable=True),
        sa.Column("home_team_name", sa.String(255), nullable=True),
        sa.Column("away_team_name", sa.String(255), nullable=True),
        sa.Column("model", sa.String(16), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("markets_json", postgresql.JSONB(), nullable=False),
        sa.Column("modules_json", postgresql.JSONB(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("today_fixture_id", "model", name="uq_cecchino_live_predictions_fixture_model"),
    )
    op.create_index("ix_cecchino_live_predictions_today_fixture_id", "cecchino_live_predictions", ["today_fixture_id"])
    op.create_index("ix_cecchino_live_predictions_provider_fixture_id", "cecchino_live_predictions", ["provider_fixture_id"])
    op.create_index("ix_cecchino_live_predictions_scan_date_model", "cecchino_live_predictions", ["scan_date", "model"])


def downgrade() -> None:
    op.drop_table("cecchino_live_predictions")
