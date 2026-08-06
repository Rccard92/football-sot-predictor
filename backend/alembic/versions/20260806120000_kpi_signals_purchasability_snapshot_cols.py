"""Add purchasability snapshot columns to cecchino_kpi_signal_activations

Revision ID: 20260806120000
Revises: 20260802120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260806120000"
down_revision: Union[str, Sequence[str], None] = "20260802120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "cecchino_kpi_signal_activations"

_COLUMNS: list[tuple[str, sa.types.TypeEngine]] = [
    ("purchasability_v3_formula_version", sa.String(length=128)),
    ("purchasability_v3_status", sa.String(length=64)),
    ("purchasability_v3_score", sa.Numeric(8, 4)),
    ("purchasability_v3_class_key", sa.String(length=32)),
    ("purchasability_v3_class_label", sa.String(length=64)),
    ("purchasability_v3_calculation_quality", sa.String(length=32)),
    ("purchasability_v3_source_snapshot_at", sa.DateTime(timezone=True)),
    ("purchasability_v3_reason_codes_json", postgresql.JSONB(astext_type=sa.Text())),
    ("purchasability_v31_candidate_version", sa.String(length=128)),
    ("purchasability_v31_formula_version", sa.String(length=128)),
    ("purchasability_v31_formula_config_version", sa.String(length=128)),
    ("purchasability_v31_audit_version", sa.String(length=128)),
    ("purchasability_v31_status", sa.String(length=64)),
    ("purchasability_v31_score", sa.Numeric(8, 4)),
    ("purchasability_v31_class_key", sa.String(length=32)),
    ("purchasability_v31_class_label", sa.String(length=64)),
    ("purchasability_v31_calculation_quality", sa.String(length=32)),
    ("purchasability_v31_historical_evidence_quality", sa.String(length=32)),
    ("purchasability_v31_source_snapshot_at", sa.DateTime(timezone=True)),
    ("purchasability_v31_generated_at", sa.DateTime(timezone=True)),
    ("purchasability_v31_execution_quote_real", sa.Boolean()),
    ("purchasability_v31_reason_codes_json", postgresql.JSONB(astext_type=sa.Text())),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for name, col_type in _COLUMNS:
        op.add_column(_TABLE, sa.Column(name, col_type, nullable=True))

    op.create_index(
        "ix_cecchino_kpi_signal_activations_purchasability_v3_status",
        _TABLE,
        ["purchasability_v3_status"],
    )
    op.create_index(
        "ix_cecchino_kpi_signal_activations_purchasability_v31_status",
        _TABLE,
        ["purchasability_v31_status"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(
        "ix_cecchino_kpi_signal_activations_purchasability_v31_status",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_cecchino_kpi_signal_activations_purchasability_v3_status",
        table_name=_TABLE,
    )
    for name, _col_type in reversed(_COLUMNS):
        op.drop_column(_TABLE, name)
