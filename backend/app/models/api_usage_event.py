"""Eventi consumo API esterne (API-Football)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PROVIDER_API_FOOTBALL = "api_football"


class ApiUsageEvent(Base):
    __tablename__ = "api_usage_events"
    __table_args__ = (
        Index("ix_api_usage_events_created_at", "created_at"),
        Index("ix_api_usage_events_scan_date", "scan_date"),
        Index("ix_api_usage_events_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_source: Mapped[str] = mapped_column(String(32), nullable=False, default=PROVIDER_API_FOOTBALL)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_params_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_params_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    negative_cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
