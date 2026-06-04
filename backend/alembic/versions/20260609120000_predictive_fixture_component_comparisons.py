"""predictive_fixture_component_comparisons

Revision ID: 20260609120000
Revises: 20260608120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260609120000"
down_revision: Union[str, Sequence[str], None] = "20260608120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "predictive_simulation_runs",
        sa.Column(
            "season_component_error_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "predictive_fixture_component_comparisons",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_key", sa.String(length=64), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("home_team_id", sa.BigInteger(), nullable=False),
        sa.Column("away_team_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "match_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "component_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["predictive_simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "fixture_id",
            "strategy_key",
            name="uq_predictive_fixture_component_comparisons_run_fixture_strategy",
        ),
    )
    op.create_index(
        "ix_predictive_fixture_component_comparisons_run_round",
        "predictive_fixture_component_comparisons",
        ["run_id", "round_number"],
        unique=False,
    )
    op.create_index(
        "ix_predictive_fixture_component_comparisons_run_strategy",
        "predictive_fixture_component_comparisons",
        ["run_id", "strategy_key"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(
        "ix_predictive_fixture_component_comparisons_run_strategy",
        table_name="predictive_fixture_component_comparisons",
    )
    op.drop_index(
        "ix_predictive_fixture_component_comparisons_run_round",
        table_name="predictive_fixture_component_comparisons",
    )
    op.drop_table("predictive_fixture_component_comparisons")
    op.drop_column("predictive_simulation_runs", "season_component_error_summary_json")
