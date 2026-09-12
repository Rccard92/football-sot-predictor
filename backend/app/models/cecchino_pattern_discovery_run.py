"""Run di scoperta Pattern walk-forward Cecchino (motore Segnali — Pattern/Formula)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String
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


class CecchinoPatternDiscoveryRun(Base, TimestampMixin):
    """Job resumibile: scoperta Pattern walk-forward per un market_key, su N stagioni.

    Ogni run addestra un albero decisionale poco profondo per fold di training
    (finestra espandibile) e valida le regole risultanti sulla stagione successiva
    (mai vista in training). Non modifica alcuna formula esistente: produce
    esclusivamente righe candidate in cecchino_discovered_patterns.
    """

    __tablename__ = "cecchino_pattern_discovery_runs"
    __table_args__ = (
        Index("ix_cecchino_pattern_disc_runs_market_status", "market_key", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    competition: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    run_ids_json: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    folds_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folds_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
