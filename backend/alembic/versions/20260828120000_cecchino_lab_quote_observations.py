"""Migration: quote_observations_json su snapshot storici V4."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260828120000_quote_obs"
down_revision = "20260806213000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cecchino_lab_historical_match_snapshots",
        sa.Column("quote_observations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_cecchino_lab_hist_snap_run_kickoff_elig",
        "cecchino_lab_historical_match_snapshots",
        ["run_id", "kickoff_at", "historical_eligibility_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cecchino_lab_hist_snap_run_kickoff_elig",
        table_name="cecchino_lab_historical_match_snapshots",
    )
    op.drop_column("cecchino_lab_historical_match_snapshots", "quote_observations_json")
