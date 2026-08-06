"""Widen GI v5 preview bundle status to String(64)

Revision ID: 20260806200000
Revises: 20260806170000

Additive migration:
- enlarge cecchino_goal_intensity_v5_preview_bundles.status from VARCHAR(32) to VARCHAR(64)
  so Phase 2C can persist frozen_external_benchmark_candidate (35 chars).

Downgrade shrinks back to VARCHAR(32) only when no status value exceeds 32 characters.
It never truncates or deletes rows.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260806200000"
down_revision: Union[str, Sequence[str], None] = "20260806170000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "cecchino_goal_intensity_v5_preview_bundles"
COLUMN = "status"


def upgrade() -> None:
    op.alter_column(
        TABLE,
        COLUMN,
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    incompatible = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE} WHERE LENGTH({COLUMN}) > 32"
        )
    ).scalar()
    if incompatible and int(incompatible) > 0:
        raise RuntimeError(
            "gi_v5_preview_bundle_status_downgrade_blocked: "
            f"{int(incompatible)} row(s) have status longer than 32 characters; "
            "refusing truncate/delete"
        )
    op.alter_column(
        TABLE,
        COLUMN,
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
