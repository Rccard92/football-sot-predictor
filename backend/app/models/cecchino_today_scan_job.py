"""Job asincrono scan giornaliero Cecchino Today."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

JOB_ACTIVE_STATUSES = frozenset({JOB_STATUS_QUEUED, JOB_STATUS_RUNNING})


class CecchinoTodayScanJob(Base, TimestampMixin):
    __tablename__ = "cecchino_today_scan_jobs"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_cecchino_today_scan_jobs_job_id"),
        Index("ix_cecchino_today_scan_jobs_scan_date_status", "scan_date", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Rome")
    force_rescan: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_STATUS_QUEUED, index=True)
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fixtures_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fixtures_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    odds_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    errors_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
