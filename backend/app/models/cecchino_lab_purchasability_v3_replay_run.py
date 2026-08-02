"""Run di replay Acquistabilità V3 isolato (Cecchino Lab)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
STATUS_CANCEL_REQUESTED = "cancel_requested"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"

ACTIVE_STATUSES = frozenset({STATUS_QUEUED, STATUS_RUNNING, STATUS_CANCEL_REQUESTED})
TERMINAL_STATUSES = frozenset(
    {
        STATUS_COMPLETED,
        STATUS_COMPLETED_WITH_WARNINGS,
        STATUS_FAILED,
        STATUS_CANCELLED,
    }
)
RESUMABLE_STATUSES = frozenset({STATUS_FAILED, STATUS_CANCELLED, STATUS_INTERRUPTED})
COMPLETED_STATUSES = frozenset({STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS})


class CecchinoLabPurchasabilityV3ReplayRun(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_purchasability_v3_replay_runs"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_cecchino_lab_p3_replay_runs_idempotency",
        ),
        Index("ix_cecchino_lab_p3_replay_runs_status", "status"),
        Index("ix_cecchino_lab_p3_replay_runs_source_scan", "source_scan_run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_scan_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_historical_scan_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=STATUS_QUEUED, index=True
    )
    replay_schema_version: Mapped[str] = mapped_column(String(96), nullable=False)
    replay_engine_version: Mapped[str] = mapped_column(String(96), nullable=False)
    candidate_version: Mapped[str] = mapped_column(String(96), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(96), nullable=False)
    audit_version: Mapped[str] = mapped_column(String(96), nullable=False)
    preflight_schema_version: Mapped[str] = mapped_column(String(96), nullable=False)
    integrity_policy_version: Mapped[str] = mapped_column(String(96), nullable=False)

    source_scan_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_git_commit_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_scan_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    snapshots_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshots_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluations_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluations_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    current_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_chronological_order: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_competition: Mapped[str | None] = mapped_column(String(128), nullable=True)

    scored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gate_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unavailable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_applicable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unclassified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    exact_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    non_replayable_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    real_quote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derived_quote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unavailable_quote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    real_performance_ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synthetic_performance_ready_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    performance_missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resume_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    preflight_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
