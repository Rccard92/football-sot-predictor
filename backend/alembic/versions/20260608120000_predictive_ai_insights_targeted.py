"""predictive_ai_insights_targeted

Revision ID: 20260608120000
Revises: 20260607120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260608120000"
down_revision: Union[str, Sequence[str], None] = "20260607120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "predictive_ai_insights",
        sa.Column("analysis_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "predictive_ai_insights",
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "predictive_ai_insights",
        sa.Column("strategy_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "predictive_ai_insights",
        sa.Column(
            "input_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "predictive_ai_insights",
        sa.Column("model_name", sa.String(length=64), nullable=True),
    )

    op.execute(
        sa.text(
            "UPDATE predictive_ai_insights SET analysis_type = 'legacy_generic' "
            "WHERE analysis_type IS NULL",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE predictive_ai_insights SET model_name = 'unknown' "
            "WHERE model_name IS NULL",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE predictive_ai_insights SET input_summary_json = '{}'::jsonb "
            "WHERE input_summary_json IS NULL",
        ),
    )

    op.alter_column("predictive_ai_insights", "analysis_type", nullable=False)
    op.alter_column("predictive_ai_insights", "input_summary_json", nullable=False)
    op.alter_column("predictive_ai_insights", "model_name", nullable=False)

    op.create_index(
        "ix_predictive_ai_insights_run_type_created",
        "predictive_ai_insights",
        ["run_id", "analysis_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_predictive_ai_insights_run_type_created", table_name="predictive_ai_insights")
    op.drop_column("predictive_ai_insights", "model_name")
    op.drop_column("predictive_ai_insights", "input_summary_json")
    op.drop_column("predictive_ai_insights", "strategy_key")
    op.drop_column("predictive_ai_insights", "fixture_id")
    op.drop_column("predictive_ai_insights", "analysis_type")
