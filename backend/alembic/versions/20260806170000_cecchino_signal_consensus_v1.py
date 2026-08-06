"""cecchino signal consensus v1 + formula version on activations

Revision ID: 20260806170000
Revises: 20260806143000

Additive migration:
- nullable consensus / formula version columns
- index (signal_formula_version, is_acquired)
- unique key includes COALESCE(signal_formula_version, legacy)

Downgrade restores the previous unique key only if no collisions would occur.
It never deletes V2 activation rows.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260806170000"
down_revision: Union[str, Sequence[str], None] = "20260806143000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_FORMULA = "cecchino_signals_matrix_v1_legacy"

_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine]] = [
    ("signal_formula_version", sa.String(length=64)),
    ("consensus_policy_version", sa.String(length=64)),
    ("formula_source_mode", sa.String(length=64)),
    ("consensus_source_group", sa.String(length=64)),
    ("consensus_eligible", sa.Boolean()),
    ("consensus_available_count", sa.Integer()),
    ("consensus_required_count", sa.Integer()),
    ("consensus_yes_count", sa.Integer()),
    ("consensus_yes_columns_json", JSONB()),
    ("consensus_passed", sa.Boolean()),
    ("is_acquired", sa.Boolean()),
    ("acquisition_status", sa.String(length=64)),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for name, col_type in _NEW_COLUMNS:
        op.add_column(
            "cecchino_signal_activations",
            sa.Column(name, col_type, nullable=True),
        )

    op.create_index(
        "ix_cecchino_signal_activations_formula_acquired",
        "cecchino_signal_activations",
        ["signal_formula_version", "is_acquired"],
    )

    op.drop_index("uq_cecchino_signal_activation_key", table_name="cecchino_signal_activations")
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_cecchino_signal_activation_key
        ON cecchino_signal_activations (
            today_fixture_id,
            model_key,
            COALESCE(signal_formula_version, '{LEGACY_FORMULA}'),
            signal_group,
            source_column,
            COALESCE(target_market_key, '')
        )
        """
    )


def downgrade() -> None:
    """Restore previous unique key only if safe; never delete V2 rows."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    collisions = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM (
                SELECT today_fixture_id, model_key, signal_group, source_column,
                       COALESCE(target_market_key, '') AS tmk
                FROM cecchino_signal_activations
                GROUP BY today_fixture_id, model_key, signal_group, source_column,
                         COALESCE(target_market_key, '')
                HAVING COUNT(*) > 1
            ) dup
            """
        )
    ).scalar()
    if int(collisions or 0) > 0:
        raise RuntimeError(
            "downgrade 20260806170000 aborted: restoring uq_cecchino_signal_activation_key "
            f"would collide on {collisions} key groups (V2 rows coexist with V1). "
            "Do not delete activation data; resolve manually before downgrade."
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

    op.drop_index(
        "ix_cecchino_signal_activations_formula_acquired",
        table_name="cecchino_signal_activations",
    )

    for name, _col_type in reversed(_NEW_COLUMNS):
        op.drop_column("cecchino_signal_activations", name)
