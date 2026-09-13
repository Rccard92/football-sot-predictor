"""cecchino v3 fase 1: run, previsioni partita e previsioni mercato

Tabelle nuove e separate: nessuna tabella V2 viene modificata.

Revision ID: 20260914090000_v3_phase1
Revises: 20260913150000_pi_profit
Create Date: 2026-09-14 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914090000_v3_phase1"
down_revision: Union[str, Sequence[str], None] = "20260913150000_pi_profit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "cecchino_v3_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_json", postgresql.JSONB(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
        sa.Column("source_git_commit", sa.String(64), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "cecchino_v3_match_predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_name", sa.String(128), nullable=False),
        sa.Column("country_group", sa.String(64), nullable=False),
        sa.Column("season_label", sa.String(32), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team", sa.String(128), nullable=False),
        sa.Column("away_team", sa.String(128), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("eval_eligible", sa.Boolean(), nullable=False),
        sa.Column("home_played", sa.Integer(), nullable=False),
        sa.Column("away_played", sa.Integer(), nullable=False),
        sa.Column("home_remaining", sa.Integer(), nullable=False),
        sa.Column("away_remaining", sa.Integer(), nullable=False),
        sa.Column("lambda_home", sa.Numeric(8, 5), nullable=False),
        sa.Column("lambda_away", sa.Numeric(8, 5), nullable=False),
        sa.Column("rho", sa.Numeric(6, 4), nullable=False),
        sa.Column("ht_share", sa.Numeric(6, 4), nullable=False),
        sa.Column("home_evidence", sa.Numeric(9, 3), nullable=False),
        sa.Column("away_evidence", sa.Numeric(9, 3), nullable=False),
        sa.Column("hyper_xi", sa.Numeric(8, 5), nullable=False),
        sa.Column("hyper_sigma", sa.Numeric(6, 3), nullable=False),
        sa.Column("ft_home_goals", sa.Integer(), nullable=False),
        sa.Column("ft_away_goals", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("run_id", "lab_match_id", name="uq_cecchino_v3_match_pred_run_match"),
    )
    op.create_index(
        "ix_cecchino_v3_match_pred_run_season",
        "cecchino_v3_match_predictions",
        ["run_id", "season_label"],
    )

    op.create_table(
        "cecchino_v3_market_predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "match_prediction_id",
            sa.BigInteger(),
            sa.ForeignKey("cecchino_v3_match_predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lab_match_id", sa.BigInteger(), nullable=False),
        sa.Column("market_key", sa.String(32), nullable=False),
        sa.Column("probability", sa.Numeric(9, 7), nullable=False),
        sa.Column("won", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_cecchino_v3_market_pred_run_market",
        "cecchino_v3_market_predictions",
        ["run_id", "market_key"],
    )
    op.create_index(
        "ix_cecchino_v3_market_pred_match",
        "cecchino_v3_market_predictions",
        ["match_prediction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cecchino_v3_market_pred_match", table_name="cecchino_v3_market_predictions")
    op.drop_index("ix_cecchino_v3_market_pred_run_market", table_name="cecchino_v3_market_predictions")
    op.drop_table("cecchino_v3_market_predictions")
    op.drop_index("ix_cecchino_v3_match_pred_run_season", table_name="cecchino_v3_match_predictions")
    op.drop_table("cecchino_v3_match_predictions")
    op.drop_table("cecchino_v3_runs")
