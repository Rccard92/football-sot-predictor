"""Add cecchino_purchasability_evaluations for Fase 5/5 validation.

Revision ID: 20260719190000
Revises: 20260718100000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260719190000"
down_revision: Union[str, Sequence[str], None] = "20260718100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_purchasability_evaluations",
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
        sa.Column("snapshot_version", sa.String(length=128), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("source_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_timestamp_verified", sa.Boolean(), nullable=True),
        sa.Column("snapshot_before_kickoff", sa.Boolean(), nullable=True),
        sa.Column("source_cohort", sa.String(length=64), nullable=False),
        sa.Column("candidate_version", sa.String(length=128), nullable=False),
        sa.Column("candidate_name", sa.String(length=128), nullable=True),
        sa.Column("feature_version", sa.String(length=128), nullable=True),
        sa.Column("market_key", sa.String(length=64), nullable=False),
        sa.Column("selection", sa.String(length=64), nullable=True),
        sa.Column("calculation_status", sa.String(length=32), nullable=True),
        sa.Column("calculation_quality", sa.String(length=32), nullable=True),
        sa.Column("purchasability_score", sa.Integer(), nullable=True),
        sa.Column("raw_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("purchasability_class", sa.String(length=64), nullable=True),
        sa.Column("phase_1_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("phase_2_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("reading", sa.Text(), nullable=True),
        sa.Column("quota_book", sa.Numeric(12, 4), nullable=True),
        sa.Column("quota_cecchino", sa.Numeric(12, 4), nullable=True),
        sa.Column("fair_book_probability", sa.Numeric(12, 6), nullable=True),
        sa.Column("prob_cecchino", sa.Numeric(12, 6), nullable=True),
        sa.Column("edge_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("rating_score", sa.Integer(), nullable=True),
        sa.Column("score_acquisto", sa.Numeric(12, 6), nullable=True),
        sa.Column("evaluation_status", sa.String(length=32), nullable=False),
        sa.Column("evaluation_reason", sa.String(length=512), nullable=True),
        sa.Column("result_home_ft", sa.Integer(), nullable=True),
        sa.Column("result_away_ft", sa.Integer(), nullable=True),
        sa.Column("result_home_ht", sa.Integer(), nullable=True),
        sa.Column("result_away_ht", sa.Integer(), nullable=True),
        sa.Column(
            "stake_units",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="1",
        ),
        sa.Column("profit_units", sa.Numeric(12, 4), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_purch_eval_today_fixture_id",
        "cecchino_purchasability_evaluations",
        ["today_fixture_id"],
    )
    op.create_index(
        "ix_purch_eval_scan_date",
        "cecchino_purchasability_evaluations",
        ["scan_date"],
    )
    op.create_index(
        "ix_purch_eval_candidate_version",
        "cecchino_purchasability_evaluations",
        ["candidate_version"],
    )
    op.create_index(
        "ix_purch_eval_market_key",
        "cecchino_purchasability_evaluations",
        ["market_key"],
    )
    op.create_index(
        "ix_purch_eval_evaluation_status",
        "cecchino_purchasability_evaluations",
        ["evaluation_status"],
    )
    op.create_index(
        "ix_purch_eval_purchasability_score",
        "cecchino_purchasability_evaluations",
        ["purchasability_score"],
    )
    op.create_index(
        "ix_purch_eval_competition_id",
        "cecchino_purchasability_evaluations",
        ["competition_id"],
    )
    op.create_index(
        "ix_purch_eval_source_cohort",
        "cecchino_purchasability_evaluations",
        ["source_cohort"],
    )
    op.create_index(
        "ix_purch_eval_promotion_eligible",
        "cecchino_purchasability_evaluations",
        ["promotion_eligible"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_purch_eval_current_key
        ON cecchino_purchasability_evaluations (
            today_fixture_id,
            candidate_version,
            market_key
        )
        WHERE is_current = true
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(
        "uq_purch_eval_current_key",
        table_name="cecchino_purchasability_evaluations",
    )
    op.drop_table("cecchino_purchasability_evaluations")
