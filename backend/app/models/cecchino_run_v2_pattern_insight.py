"""Tabelle Pattern Insights (Run V2) — separate dal Pattern Grid originale
(cecchino_pattern_grid_*): fonte dati diversa (Run V2, non i run storici
17/19/20/21), vocabolario piu' ampio (tiri/corner/cartellini/arbitro),
e per ora una sola stagione (nessuna validazione a stadi possibile finche'
non esistono piu' stagioni Run V2)."""

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
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_RUNNING)

TARGET_TYPE_MARKET = "market"
TARGET_TYPE_SYNTHETIC = "synthetic"


class CecchinoRunV2PatternInsightRun(Base, TimestampMixin):
    __tablename__ = "cecchino_run_v2_pattern_insight_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_v2_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_run_v2_runs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    targets_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    targets_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_target_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CecchinoRunV2PatternInsightCandidate(Base, TimestampMixin):
    __tablename__ = "cecchino_run_v2_pattern_insight_candidates"
    __table_args__ = (
        Index("ix_cecchino_run_v2_pi_cand_run", "insight_run_id"),
        Index("ix_cecchino_run_v2_pi_cand_target", "target_type", "target_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    insight_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_pattern_insight_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_key: Mapped[str] = mapped_column(String(32), nullable=False)
    target_label: Mapped[str] = mapped_column(String(128), nullable=False)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    filters_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    filters_text: Mapped[str] = mapped_column(Text, nullable=False)
    filters_text_human: Mapped[str] = mapped_column(Text, nullable=False)
    refined_from_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    n: Mapped[int] = mapped_column(Integer, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    roi_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True, index=True)
    avg_quota: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    baseline_win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True, index=True)


VERDICT_CONFIRMED = "confirmed"
VERDICT_ATTENUATED = "attenuated"
VERDICT_REJECTED = "rejected"
VERDICT_INSUFFICIENT = "insufficient_sample"


class CecchinoRunV2PatternValidationRun(Base, TimestampMixin):
    """Verifica fuori campione dei pattern di un'analisi su una stagione Run V2
    successiva, mai vista in fase di scoperta."""

    __tablename__ = "cecchino_run_v2_pattern_validation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    insight_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_pattern_insight_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_v2_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_run_v2_runs.id", ondelete="CASCADE"), nullable=False
    )
    season_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    targets_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    targets_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_target_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CecchinoRunV2PatternValidation(Base, TimestampMixin):
    __tablename__ = "cecchino_run_v2_pattern_validations"
    __table_args__ = (
        Index("ix_cecchino_run_v2_pval_run_verdict", "validation_run_id", "verdict"),
        Index("ix_cecchino_run_v2_pval_candidate", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_pattern_validation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_pattern_insight_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    roi_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 3), nullable=True)
    profit_units: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    avg_quota: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    baseline_win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 3), nullable=True)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    null_confirm_prob: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
