"""Righe risultato per fixture del benchmark storico Goal Intensity V4 vs V5."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoLabGoalIntensityBenchmarkRow(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_goal_intensity_benchmark_rows"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "historical_snapshot_id",
            name="uq_cecchino_lab_gi_bench_rows_job_snap",
        ),
        Index("ix_cecchino_lab_gi_bench_rows_job", "job_id"),
        Index("ix_cecchino_lab_gi_bench_rows_snap", "historical_snapshot_id"),
        Index("ix_cecchino_lab_gi_bench_rows_lab_match", "lab_match_id"),
        Index("ix_cecchino_lab_gi_bench_rows_competition", "competition_name"),
        Index("ix_cecchino_lab_gi_bench_rows_kickoff", "kickoff_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_goal_intensity_benchmark_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    historical_snapshot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lab_match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    today_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    local_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    competition_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    included_in_main_cohort: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prediction_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    target_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evaluation_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
