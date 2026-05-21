"""tracked_betting_picks — snapshot definitiva pre-match per monitoraggio giocate

Revision ID: 20260526120000
Revises: 20260525120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260526120000"
down_revision: Union[str, Sequence[str], None] = "20260525120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "tracked_betting_picks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("market_id", sa.String(length=64), nullable=False),
        sa.Column("market_label", sa.String(length=128), nullable=False),
        sa.Column("pick_type", sa.String(length=32), nullable=False),
        sa.Column("suggested_pick", sa.String(length=128), nullable=True),
        sa.Column("line_value", sa.Float(), nullable=True),
        sa.Column("predicted_home_sot", sa.Float(), nullable=True),
        sa.Column("predicted_away_sot", sa.Float(), nullable=True),
        sa.Column("predicted_total_sot", sa.Float(), nullable=True),
        sa.Column("confidence_label", sa.String(length=32), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("lineup_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lineup_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prediction_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("result_home_sot", sa.Float(), nullable=True),
        sa.Column("result_away_sot", sa.Float(), nullable=True),
        sa.Column("result_total_sot", sa.Float(), nullable=True),
        sa.Column("fixture_status", sa.String(length=64), nullable=True),
        sa.Column("elapsed", sa.Integer(), nullable=True),
        sa.Column("score_home", sa.Integer(), nullable=True),
        sa.Column("score_away", sa.Integer(), nullable=True),
        sa.Column("raw_prediction_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_betting_advice_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tracked_betting_picks_fixture_id"),
        "tracked_betting_picks",
        ["fixture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tracked_betting_picks_model_id"),
        "tracked_betting_picks",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tracked_betting_picks_source"),
        "tracked_betting_picks",
        ["source"],
        unique=False,
    )
    op.create_index(
        "uq_tracked_betting_picks_auto_pre_match",
        "tracked_betting_picks",
        ["fixture_id", "model_id", "market_id", "pick_type", "source"],
        unique=True,
        postgresql_where=sa.text("source = 'auto_pre_match'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_tracked_betting_picks_auto_pre_match", table_name="tracked_betting_picks")
    op.drop_index(op.f("ix_tracked_betting_picks_source"), table_name="tracked_betting_picks")
    op.drop_index(op.f("ix_tracked_betting_picks_model_id"), table_name="tracked_betting_picks")
    op.drop_index(op.f("ix_tracked_betting_picks_fixture_id"), table_name="tracked_betting_picks")
    op.drop_table("tracked_betting_picks")
