"""Snapshot aggregato League Pattern Analysis (append-only, versionato)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_BUILDING = "building"


class CecchinoLabLeaguePatternAnalysisSnapshot(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_league_pattern_analysis_snapshots"
    __table_args__ = (
        Index(
            "ix_lpa_snap_version_status_generated",
            "analysis_version",
            "status",
            "generated_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_version: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    analysis_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    source_run_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    source_seasons: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    scan_versions: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    preset_registry_version: Mapped[str] = mapped_column(String(96), nullable=False)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    analysis_dataset_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    future_oos_season: Mapped[str] = mapped_column(String(32), nullable=False)
    future_oos_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    source_enrichment_batch_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    market_universe_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="base_v1"
    )

    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    competition_regimes_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    global_patterns_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    pattern_league_matrix_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    specializations_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    incompatibilities_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    league_native_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    methodology_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
