"""Add Balance v5 readiness snapshots + governance decisions (Step 2C).

Revision ID: 20260720180000
Revises: 20260720120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720180000"
down_revision: Union[str, Sequence[str], None] = "20260720120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "cecchino_balance_v5_readiness_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("readiness_version", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=True),
        sa.Column("analysis_version", sa.String(length=128), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("competition_id", sa.BigInteger(), nullable=True),
        sa.Column("prospective_settled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prospective_pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prospective_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temporal_folds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("operational_status", sa.String(length=64), nullable=False),
        sa.Column("scientific_maturity", sa.String(length=64), nullable=False),
        sa.Column("manual_review_status", sa.String(length=64), nullable=False),
        sa.Column("signals_integration_status", sa.String(length=64), nullable=False),
        sa.Column("current_decision", sa.String(length=64), nullable=False),
        sa.Column("pillar_statuses_json", sa.Text(), nullable=True),
        sa.Column("technical_gates_json", sa.Text(), nullable=True),
        sa.Column("scientific_gates_json", sa.Text(), nullable=True),
        sa.Column("progress_json", sa.Text(), nullable=True),
        sa.Column("readiness_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_date",
            "policy_version",
            "competition_id",
            name="uq_balance_v5_readiness_snap_date_policy_comp",
        ),
    )
    op.create_index(
        "ix_balance_v5_readiness_snap_date",
        "cecchino_balance_v5_readiness_snapshots",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_balance_v5_readiness_snap_policy",
        "cecchino_balance_v5_readiness_snapshots",
        ["policy_version"],
    )
    op.create_index(
        "ix_balance_v5_readiness_snap_comp",
        "cecchino_balance_v5_readiness_snapshots",
        ["competition_id"],
    )

    op.create_table(
        "cecchino_balance_v5_governance_decisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("governance_version", sa.String(length=128), nullable=False),
        sa.Column("readiness_version", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column(
            "decision_status",
            sa.String(length=32),
            nullable=False,
            server_default="recorded",
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("evidence_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("confirmed_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_balance_v5_gov_decision",
        "cecchino_balance_v5_governance_decisions",
        ["decision"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_table("cecchino_balance_v5_governance_decisions")
    op.drop_table("cecchino_balance_v5_readiness_snapshots")
