"""cecchino v3 passo 3: valutatore di mercato

Revision ID: 20260914180000_v3_evaluator
Revises: 20260914160000_v3_indices
Create Date: 2026-09-14 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914180000_v3_evaluator"
down_revision: Union[str, Sequence[str], None] = "20260914160000_v3_indices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_v3_evaluator_runs",
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
        "cecchino_v3_evaluator_plays",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "evaluator_run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_evaluator_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("season_label", sa.String(32), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("competition_name", sa.String(128), nullable=False),
        sa.Column("home_team", sa.String(128), nullable=False),
        sa.Column("away_team", sa.String(128), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("market_key", sa.String(32), nullable=False),
        sa.Column("odds", sa.Numeric(10, 3), nullable=False),
        sa.Column("p_v3", sa.Numeric(9, 7), nullable=False),
        sa.Column("p_book", sa.Numeric(9, 7), nullable=False),
        sa.Column("p_eval", sa.Numeric(9, 7), nullable=True),
        sa.Column("edge", sa.Numeric(9, 5), nullable=False),
        sa.Column("won", sa.Boolean(), nullable=False),
        sa.Column("profit", sa.Numeric(9, 3), nullable=False),
    )
    op.create_index(
        "ix_cecchino_v3_eval_play_run_strategy_season",
        "cecchino_v3_evaluator_plays",
        ["evaluator_run_id", "strategy", "season_label"],
    )


def downgrade() -> None:
    op.drop_index("ix_cecchino_v3_eval_play_run_strategy_season", table_name="cecchino_v3_evaluator_plays")
    op.drop_table("cecchino_v3_evaluator_plays")
    op.drop_table("cecchino_v3_evaluator_runs")
