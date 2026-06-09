"""cecchino_signal_activations model_key for weight model backtest

Revision ID: 20260620120000
Revises: 20260619120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260620120000"
down_revision: Union[str, Sequence[str], None] = "20260619120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "cecchino_signal_activations",
        sa.Column("model_key", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "cecchino_signal_activations",
        sa.Column("model_label", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "cecchino_signal_activations",
        sa.Column("weights_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "cecchino_signal_activations",
        sa.Column("weights_json", JSONB(), nullable=True),
    )

    op.execute(
        """
        UPDATE cecchino_signal_activations
        SET
            model_key = 'F',
            model_label = 'F – Conservativo',
            weights_version = 'model_F_30_30_20_20',
            weights_json = '{"totals": 0.30, "home_away": 0.30, "last6_totals": 0.20, "last5_home_away": 0.20}'::jsonb
        WHERE model_key IS NULL
        """
    )

    op.alter_column(
        "cecchino_signal_activations",
        "model_key",
        nullable=False,
        server_default="F",
    )

    op.create_index(
        "ix_cecchino_signal_activations_model_key",
        "cecchino_signal_activations",
        ["model_key"],
    )

    op.drop_index("uq_cecchino_signal_activation_key", table_name="cecchino_signal_activations")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_cecchino_signal_activation_key
        ON cecchino_signal_activations (
            today_fixture_id,
            model_key,
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
    op.drop_index("ix_cecchino_signal_activations_model_key", table_name="cecchino_signal_activations")
    op.drop_column("cecchino_signal_activations", "weights_json")
    op.drop_column("cecchino_signal_activations", "weights_version")
    op.drop_column("cecchino_signal_activations", "model_label")
    op.drop_column("cecchino_signal_activations", "model_key")
