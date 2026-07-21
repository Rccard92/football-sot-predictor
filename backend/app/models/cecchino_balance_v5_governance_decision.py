"""Decisioni di governance Balance v5 — Step 2C."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CecchinoBalanceV5GovernanceDecision(Base):
    __tablename__ = "cecchino_balance_v5_governance_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    governance_version: Mapped[str] = mapped_column(String(128), nullable=False)
    readiness_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_status: Mapped[str] = mapped_column(String(32), nullable=False, default="recorded")
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
