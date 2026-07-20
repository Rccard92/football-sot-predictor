"""Add cecchino_balance_v5_evaluations for Fase 2/3 Step 2A empirical dataset.

Revision ID: 20260720120000
Revises: 20260719190000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720120000"
down_revision: Union[str, Sequence[str], None] = "20260719190000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_balance_v5_evaluations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("today_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("local_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("competition_id", sa.BigInteger(), nullable=True),
        sa.Column("scan_date", sa.Date(), nullable=True),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("country_name", sa.String(length=128), nullable=True),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("home_team_name", sa.String(length=255), nullable=True),
        sa.Column("away_team_name", sa.String(length=255), nullable=True),
        sa.Column("empirical_dataset_version", sa.String(length=128), nullable=False),
        sa.Column("balance_version", sa.String(length=128), nullable=False),
        sa.Column("snapshot_version", sa.String(length=128), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("source_mode", sa.String(length=128), nullable=True),
        sa.Column("source_cohort", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pre_match_verified", sa.Boolean(), nullable=True),
        sa.Column("book_verified", sa.Boolean(), nullable=True),
        sa.Column("warning_codes", sa.Text(), nullable=True),
        sa.Column("f36_index", sa.Numeric(12, 4), nullable=True),
        sa.Column("f36_class", sa.String(length=64), nullable=True),
        sa.Column("dominance_index", sa.Numeric(12, 4), nullable=True),
        sa.Column("dominance_class", sa.String(length=64), nullable=True),
        sa.Column("dominance_selection", sa.String(length=16), nullable=True),
        sa.Column("draw_credibility_index", sa.Numeric(12, 4), nullable=True),
        sa.Column("draw_credibility_class", sa.String(length=64), nullable=True),
        sa.Column("gap_index", sa.Numeric(12, 4), nullable=True),
        sa.Column("gap_class", sa.String(length=64), nullable=True),
        sa.Column("prob_1_norm", sa.Numeric(12, 6), nullable=True),
        sa.Column("prob_x_norm", sa.Numeric(12, 6), nullable=True),
        sa.Column("prob_2_norm", sa.Numeric(12, 6), nullable=True),
        sa.Column("book_prob_1", sa.Numeric(12, 6), nullable=True),
        sa.Column("book_prob_x", sa.Numeric(12, 6), nullable=True),
        sa.Column("book_prob_2", sa.Numeric(12, 6), nullable=True),
        sa.Column("evaluation_status", sa.String(length=32), nullable=False),
        sa.Column("evaluation_reason", sa.String(length=512), nullable=True),
        sa.Column("ft_home", sa.Integer(), nullable=True),
        sa.Column("ft_away", sa.Integer(), nullable=True),
        sa.Column("ht_home", sa.Integer(), nullable=True),
        sa.Column("ht_away", sa.Integer(), nullable=True),
        sa.Column("outcome_1x2", sa.String(length=16), nullable=True),
        sa.Column("is_draw", sa.Boolean(), nullable=True),
        sa.Column("total_goals", sa.Integer(), nullable=True),
        sa.Column("absolute_goal_difference", sa.Integer(), nullable=True),
        sa.Column("dominance_selection_hit", sa.Boolean(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "analysis_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "promotion_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.ForeignKeyConstraint(
            ["today_fixture_id"],
            ["cecchino_today_fixtures.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "today_fixture_id",
            "balance_version",
            "snapshot_hash",
            name="uq_balance_v5_eval_fixture_version_hash",
        ),
    )
    for name, cols in (
        ("ix_bal_v5_eval_today_fixture_id", ["today_fixture_id"]),
        ("ix_bal_v5_eval_scan_date", ["scan_date"]),
        ("ix_bal_v5_eval_competition_id", ["competition_id"]),
        ("ix_bal_v5_eval_source_cohort", ["source_cohort"]),
        ("ix_bal_v5_eval_evaluation_status", ["evaluation_status"]),
        ("ix_bal_v5_eval_f36_class", ["f36_class"]),
        ("ix_bal_v5_eval_dominance_class", ["dominance_class"]),
        ("ix_bal_v5_eval_draw_cred_class", ["draw_credibility_class"]),
        ("ix_bal_v5_eval_gap_class", ["gap_class"]),
        ("ix_bal_v5_eval_dominance_selection", ["dominance_selection"]),
        ("ix_bal_v5_eval_is_current", ["is_current"]),
        ("ix_bal_v5_eval_balance_version", ["balance_version"]),
        ("ix_bal_v5_eval_analysis_eligible", ["analysis_eligible"]),
        ("ix_bal_v5_eval_promotion_eligible", ["promotion_eligible"]),
    ):
        op.create_index(name, "cecchino_balance_v5_evaluations", cols)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("cecchino_balance_v5_evaluations")
