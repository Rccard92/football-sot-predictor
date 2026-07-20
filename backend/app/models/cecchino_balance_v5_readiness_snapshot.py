"""Snapshot giornaliero readiness Balance v5 — Step 2C."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoBalanceV5ReadinessSnapshot(Base, TimestampMixin):
    __tablename__ = "cecchino_balance_v5_readiness_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "policy_version",
            "competition_id",
            name="uq_balance_v5_readiness_snap_date_policy_comp",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    readiness_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dataset_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analysis_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    competition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    prospective_settled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prospective_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prospective_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    temporal_folds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    operational_status: Mapped[str] = mapped_column(String(64), nullable=False)
    scientific_maturity: Mapped[str] = mapped_column(String(64), nullable=False)
    manual_review_status: Mapped[str] = mapped_column(String(64), nullable=False)
    signals_integration_status: Mapped[str] = mapped_column(String(64), nullable=False)
    current_decision: Mapped[str] = mapped_column(String(64), nullable=False)

    pillar_statuses_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_gates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scientific_gates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    readiness_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
