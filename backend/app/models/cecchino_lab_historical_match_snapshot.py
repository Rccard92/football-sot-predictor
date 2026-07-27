"""Snapshot pre-match storico Cecchino Lab."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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


class CecchinoLabHistoricalMatchSnapshot(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_historical_match_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "lab_match_id",
            name="uq_cecchino_lab_hist_snap_run_match",
        ),
        Index("ix_cecchino_lab_hist_snap_run_id", "run_id"),
        Index("ix_cecchino_lab_hist_snap_lab_match_id", "lab_match_id"),
        Index("ix_cecchino_lab_hist_snap_eligibility", "historical_eligibility_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_historical_scan_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    lab_match_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    competition_name: Mapped[str] = mapped_column(String(128), nullable=False)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    away_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chronological_order: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    historical_eligibility_status: Mapped[str] = mapped_column(String(64), nullable=False)
    historical_eligibility_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    blocking_reasons_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    module_availability_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cecchino_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    historical_kpi_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    signals_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    balance_v5_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    goal_intensity_compatibility_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    purchasability_compatibility_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    quote_sources_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pre_match_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pre_match_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_attached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settlement_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    settlement_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
