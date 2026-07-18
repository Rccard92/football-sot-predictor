"""Bundle e snapshot Preview Intensità Goal v5 — Fase 2A (research)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

PREVIEW_BUNDLE_VERSION = "cecchino_goal_intensity_v5_preview_v1_1"
BUNDLE_STATUS_ACTIVE = "active"
BUNDLE_STATUS_SUPERSEDED = "superseded"

SNAPSHOT_PENDING = "pending"
SNAPSHOT_LOCKED = "locked"
SNAPSHOT_COMPLETED = "completed"
SNAPSHOT_INCOMPLETE = "incomplete"
SNAPSHOT_ERROR = "error"


class CecchinoGoalIntensityV5PreviewBundle(Base, TimestampMixin):
    __tablename__ = "cecchino_goal_intensity_v5_preview_bundles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    candidate_indices_version: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fixture_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    targets_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalization_method: Mapped[str] = mapped_column(String(64), nullable=False)
    normalization_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    calibration_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    candidate_definitions_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    retrospective_date_from: Mapped[date] = mapped_column(Date, nullable=False)
    retrospective_date_to: Mapped[date] = mapped_column(Date, nullable=False)
    first_prospective_scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=BUNDLE_STATUS_ACTIVE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class CecchinoGoalIntensityV5PreviewSnapshot(Base, TimestampMixin):
    __tablename__ = "cecchino_goal_intensity_v5_preview_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "bundle_id",
            "today_fixture_id",
            name="uq_gi_v5_preview_bundle_today_fixture",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_goal_intensity_v5_preview_bundles.id"),
        nullable=False,
        index=True,
    )
    today_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    local_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    provider_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    competition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    home_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    competition_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    eligibility_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eligibility_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eligibility_reason_codes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    feature_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    history_sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    xg_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    xg_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    pillar_scores_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    candidate_scores_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    calibrated_predictions_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    primary_candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenger_candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    diagnostic_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    candidate_definition_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalization_hashes_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    no_target_used_in_score: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    snapshot_status: Mapped[str] = mapped_column(String(32), nullable=False, default=SNAPSHOT_PENDING, index=True)
    preview_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    diagnostic_reason_codes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    first_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    goals_home_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_away_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_goals_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_ge_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_ge_3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    btts_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_attached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
