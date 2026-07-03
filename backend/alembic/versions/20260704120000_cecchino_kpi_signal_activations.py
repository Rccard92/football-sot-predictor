"""cecchino_kpi_signal_activations table

Revision ID: 20260704120000
Revises: 20260620120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260704120000"
down_revision: Union[str, Sequence[str], None] = "20260620120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_kpi_signal_activations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("today_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("country_name", sa.String(length=128), nullable=True),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("home_team_name", sa.String(length=255), nullable=True),
        sa.Column("away_team_name", sa.String(length=255), nullable=True),
        sa.Column("kpi_version", sa.String(length=64), nullable=True),
        sa.Column("kpi_row_key", sa.String(length=64), nullable=False),
        sa.Column("selection_label", sa.String(length=128), nullable=False),
        sa.Column("normalized_market", sa.String(length=64), nullable=False),
        sa.Column("selection_key", sa.String(length=64), nullable=False),
        sa.Column("rating_score", sa.Integer(), nullable=False),
        sa.Column("rating_label", sa.String(length=64), nullable=True),
        sa.Column("rating_bucket", sa.String(length=16), nullable=False),
        sa.Column("quota_book", sa.Numeric(12, 4), nullable=False),
        sa.Column("quota_cecchino", sa.Numeric(12, 4), nullable=True),
        sa.Column("prob_book", sa.Numeric(12, 4), nullable=True),
        sa.Column("prob_cecchino", sa.Numeric(12, 4), nullable=True),
        sa.Column("edge_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("score_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("evaluation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("evaluation_reason", sa.String(length=512), nullable=True),
        sa.Column("result_home_ft", sa.Integer(), nullable=True),
        sa.Column("result_away_ft", sa.Integer(), nullable=True),
        sa.Column("result_home_ht", sa.Integer(), nullable=True),
        sa.Column("result_away_ht", sa.Integer(), nullable=True),
        sa.Column("stake_units", sa.Numeric(12, 4), nullable=False, server_default="1"),
        sa.Column("profit_units", sa.Numeric(12, 4), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["today_fixture_id"],
            ["cecchino_today_fixtures.id"],
            name="fk_cecchino_kpi_signal_activations_today_fixture",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_kpi_signal_activations_scan_date",
        "cecchino_kpi_signal_activations",
        ["scan_date"],
    )
    op.create_index(
        "ix_cecchino_kpi_signal_activations_rating_bucket",
        "cecchino_kpi_signal_activations",
        ["rating_bucket"],
    )
    op.create_index(
        "ix_cecchino_kpi_signal_activations_evaluation_status",
        "cecchino_kpi_signal_activations",
        ["evaluation_status"],
    )
    op.create_index(
        "ix_cecchino_kpi_signal_activations_today_fixture_id",
        "cecchino_kpi_signal_activations",
        ["today_fixture_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_cecchino_kpi_signal_activation_key
        ON cecchino_kpi_signal_activations (
            today_fixture_id,
            normalized_market,
            selection_key
        )
        WHERE is_current = true
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_cecchino_kpi_signal_activation_key", table_name="cecchino_kpi_signal_activations")
    op.drop_table("cecchino_kpi_signal_activations")
