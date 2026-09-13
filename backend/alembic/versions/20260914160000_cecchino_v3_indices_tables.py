"""cecchino v3 passo 2: indici a 360 gradi per partita

Revision ID: 20260914160000_v3_indices
Revises: 20260914140000_v3_lookup_idx
Create Date: 2026-09-14 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914160000_v3_indices"
down_revision: Union[str, Sequence[str], None] = "20260914140000_v3_lookup_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_v3_index_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("config_json", postgresql.JSONB(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
        sa.Column("source_git_commit", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cecchino_v3_match_indices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "index_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_index_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_name", sa.String(128), nullable=False),
        sa.Column("season_label", sa.String(32), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team", sa.String(128), nullable=False),
        sa.Column("away_team", sa.String(128), nullable=False),
        sa.Column("reliability", sa.Numeric(5, 1), nullable=True),
        sa.Column("reliability_class", sa.String(16), nullable=True),
        sa.Column("equilibrio_class", sa.String(16), nullable=True),
        sa.Column("pareggio_class", sa.String(16), nullable=True),
        sa.Column("intensita_class", sa.String(16), nullable=True),
        sa.Column("indices_json", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("index_run_id", "lab_match_id", name="uq_cecchino_v3_match_index_run_match"),
    )
    op.create_index(
        "ix_cecchino_v3_match_index_run_comp_season",
        "cecchino_v3_match_indices",
        ["index_run_id", "competition_name", "season_label"],
    )


def downgrade() -> None:
    op.drop_index("ix_cecchino_v3_match_index_run_comp_season", table_name="cecchino_v3_match_indices")
    op.drop_table("cecchino_v3_match_indices")
    op.drop_table("cecchino_v3_index_runs")
