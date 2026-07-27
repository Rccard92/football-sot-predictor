"""Run di scansione storica Cecchino Lab."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = frozenset({STATUS_PENDING, STATUS_RUNNING})
TERMINAL_STATUSES = frozenset(
    {
        STATUS_COMPLETED,
        STATUS_COMPLETED_WITH_WARNINGS,
        STATUS_FAILED,
        STATUS_CANCELLED,
    }
)


class CecchinoLabHistoricalScanRun(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_historical_scan_runs"
    __table_args__ = (
        Index("ix_cecchino_lab_hist_scan_runs_season_status", "season_label", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING, index=True)
    scan_version: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_competition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    matches_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_eligible_core: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_excluded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    quote_policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    module_policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    preflight_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
