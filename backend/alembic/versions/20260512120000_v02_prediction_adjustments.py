"""v0.2 prediction adjustments table

Revision ID: 20260512120000
Revises: 20260511120000
Create Date: 2026-05-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260512120000"
down_revision: Union[str, Sequence[str], None] = "20260511120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector: sa.Inspector, bind) -> set[str]:
    if bind.dialect.name == "postgresql":
        return set(inspector.get_table_names(schema="public"))
    return set(inspector.get_table_names())


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in _table_names(inspector, bind)


def upgrade() -> None:
    if not table_exists("team_sot_prediction_adjustments"):
        op.create_table(
            "team_sot_prediction_adjustments",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("prediction_id", sa.BigInteger(), nullable=False),
            sa.Column("fixture_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", sa.BigInteger(), nullable=False),
            sa.Column("model_version", sa.String(length=64), nullable=False),
            sa.Column("baseline_expected_sot", sa.Float(), nullable=False),
            sa.Column("player_adjustment", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("h2h_adjustment", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("motivation_adjustment", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("availability_adjustment", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("total_adjustment", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("adjusted_expected_sot", sa.Float(), nullable=False),
            sa.Column("adjustment_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["prediction_id"], ["team_sot_predictions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "fixture_id",
                "team_id",
                "model_version",
                name="uq_team_sot_prediction_adjustments_fixture_team_model",
            ),
        )
        op.create_index(
            op.f("ix_team_sot_prediction_adjustments_prediction_id"),
            "team_sot_prediction_adjustments",
            ["prediction_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_team_sot_prediction_adjustments_fixture_id"),
            "team_sot_prediction_adjustments",
            ["fixture_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_team_sot_prediction_adjustments_team_id"),
            "team_sot_prediction_adjustments",
            ["team_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_team_sot_prediction_adjustments_model_version"),
            "team_sot_prediction_adjustments",
            ["model_version"],
            unique=False,
        )


def downgrade() -> None:
    if table_exists("team_sot_prediction_adjustments"):
        op.drop_index(
            op.f("ix_team_sot_prediction_adjustments_model_version"),
            table_name="team_sot_prediction_adjustments",
        )
        op.drop_index(
            op.f("ix_team_sot_prediction_adjustments_team_id"),
            table_name="team_sot_prediction_adjustments",
        )
        op.drop_index(
            op.f("ix_team_sot_prediction_adjustments_fixture_id"),
            table_name="team_sot_prediction_adjustments",
        )
        op.drop_index(
            op.f("ix_team_sot_prediction_adjustments_prediction_id"),
            table_name="team_sot_prediction_adjustments",
        )
        op.drop_table("team_sot_prediction_adjustments")
