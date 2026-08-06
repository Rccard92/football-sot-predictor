"""Job persistita di benchmark storico Goal Intensity V4 vs V5 (Cecchino Lab)."""

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

STATUS_PREVIEW = "preview"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCEL_REQUESTED = "cancel_requested"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = frozenset({STATUS_QUEUED, STATUS_RUNNING, STATUS_CANCEL_REQUESTED})
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED})
RESUMABLE_STATUSES = frozenset({STATUS_FAILED, STATUS_CANCELLED})
COMPLETED_STATUSES = frozenset({STATUS_COMPLETED})

MODE_PILOT = "pilot"
MODE_FULL = "full"

JOB_VERSION = "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1"
REQUIRED_BUNDLE_VERSION = "cecchino_goal_intensity_v5_candidate_bundle_v2_1"

CONFIRM_PILOT = "RUN_GOAL_INTENSITY_HISTORICAL_BENCHMARK_PILOT"
CONFIRM_FULL = "RUN_GOAL_INTENSITY_HISTORICAL_BENCHMARK_FULL"

DEFAULT_PILOT_SIZE = 300
DEFAULT_RANDOM_SEED = 42
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 250
MIN_BATCH_SIZE = 10


class CecchinoLabGoalIntensityBenchmarkJob(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_goal_intensity_benchmark_jobs"
    __table_args__ = (
        UniqueConstraint("job_key", name="uq_cecchino_lab_gi_bench_jobs_job_key"),
        Index("ix_cecchino_lab_gi_bench_jobs_run", "historical_run_id"),
        Index("ix_cecchino_lab_gi_bench_jobs_status", "status"),
        Index("ix_cecchino_lab_gi_bench_jobs_bundle", "bundle_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    historical_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_historical_scan_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bundle_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_goal_intensity_v5_preview_bundles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_version: Mapped[str] = mapped_column(String(128), nullable=False, default=JOB_VERSION)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_QUEUED)
    independence_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_key: Mapped[str] = mapped_column(String(160), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_RANDOM_SEED)
    requested_sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_snapshots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eligible_snapshots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_snapshots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_snapshots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paired_complete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    params_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    preflight_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    missing_by_reason_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    bundle_definition_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_fixture_ids_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
