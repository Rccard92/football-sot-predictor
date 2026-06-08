"""cecchino_signal_activations table

Revision ID: 20260619120000
Revises: 20260618120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260619120000"
down_revision: Union[str, Sequence[str], None] = "20260618120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_signal_activations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("today_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("local_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_source", sa.String(length=32), nullable=False, server_default="api_football"),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("country_name", sa.String(length=128), nullable=True),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("home_team_name", sa.String(length=255), nullable=True),
        sa.Column("away_team_name", sa.String(length=255), nullable=True),
        sa.Column("signal_group", sa.String(length=64), nullable=False),
        sa.Column("signal_label", sa.String(length=128), nullable=False),
        sa.Column("source_column", sa.String(length=32), nullable=False),
        sa.Column("signal_value", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("raw_signal_value", sa.String(length=8), nullable=True),
        sa.Column("f32", sa.Numeric(12, 4), nullable=True),
        sa.Column("f33", sa.Numeric(12, 4), nullable=True),
        sa.Column("f34", sa.Numeric(12, 4), nullable=True),
        sa.Column("f35", sa.Numeric(12, 4), nullable=True),
        sa.Column("f36", sa.Numeric(12, 4), nullable=True),
        sa.Column("target_market_key", sa.String(length=64), nullable=True),
        sa.Column("target_market_label", sa.String(length=128), nullable=True),
        sa.Column("target_period", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("evaluation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("evaluation_reason", sa.String(length=512), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ht_home_goals", sa.Integer(), nullable=True),
        sa.Column("ht_away_goals", sa.Integer(), nullable=True),
        sa.Column("ft_home_goals", sa.Integer(), nullable=True),
        sa.Column("ft_away_goals", sa.Integer(), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=True),
        sa.Column("quota_book", sa.Numeric(12, 4), nullable=True),
        sa.Column("quota_cecchino", sa.Numeric(12, 4), nullable=True),
        sa.Column("prob_book", sa.Numeric(12, 4), nullable=True),
        sa.Column("prob_cecchino", sa.Numeric(12, 4), nullable=True),
        sa.Column("edge_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["today_fixture_id"],
            ["cecchino_today_fixtures.id"],
            name="fk_cecchino_signal_activations_today_fixture",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_signal_activations_scan_date",
        "cecchino_signal_activations",
        ["scan_date"],
    )
    op.create_index(
        "ix_cecchino_signal_activations_evaluation_status",
        "cecchino_signal_activations",
        ["evaluation_status"],
    )
    op.create_index(
        "ix_cecchino_signal_activations_signal_group_column",
        "cecchino_signal_activations",
        ["signal_group", "source_column"],
    )
    op.create_index(
        "ix_cecchino_signal_activations_today_fixture_id",
        "cecchino_signal_activations",
        ["today_fixture_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_cecchino_signal_activation_key
        ON cecchino_signal_activations (
            today_fixture_id,
            signal_group,
            source_column,
            COALESCE(target_market_key, '')
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_cecchino_signal_activation_key", table_name="cecchino_signal_activations")
    op.drop_table("cecchino_signal_activations")
