"""Master Pattern: pattern vincenti 4/4 di ogni modello (V2, V2.5, V3), con versione del motore."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

MASTER_STATUS_PENDING = "pending"
MASTER_STATUS_RUNNING = "running"
MASTER_STATUS_COMPLETED = "completed"
MASTER_STATUS_FAILED = "failed"
MASTER_ACTIVE_STATUSES = (MASTER_STATUS_PENDING, MASTER_STATUS_RUNNING)


class CecchinoMasterPatternBuild(Base, TimestampMixin):
    __tablename__ = "cecchino_master_pattern_builds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=MASTER_STATUS_PENDING)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CecchinoMasterPattern(Base):
    __tablename__ = "cecchino_master_patterns"
    __table_args__ = (
        Index("ix_cecchino_master_pattern_build_type", "build_id", "target_type", "target_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    build_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_master_pattern_builds.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_key: Mapped[str] = mapped_column(String(32), nullable=False)
    target_label: Mapped[str] = mapped_column(String(128), nullable=False)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    direction: Mapped[int] = mapped_column(Integer, nullable=False)
    market_label: Mapped[str] = mapped_column(String(128), nullable=False)
    conditions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    conditions_text: Mapped[str] = mapped_column(Text, nullable=False)
    seasons_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    total_n: Mapped[int] = mapped_column(Integer, nullable=False)
    total_wins: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    profit_units: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    roi_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    avg_quota: Mapped[Decimal | None] = mapped_column(Numeric(7, 3), nullable=True)
    avg_deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    chance_p: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
