"""Modelli laboratorio predittivo persistente v3.1."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.competition import Competition


class PredictiveSimulationRun(Base, TimestampMixin):
    __tablename__ = "predictive_simulation_runs"
    __table_args__ = (
        Index(
            "ix_predictive_simulation_runs_comp_season_created",
            "competition_id",
            "season_year",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    season_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full_lab", server_default="full_lab")
    model_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v3.1", server_default="v3.1")
    strategy_status_filter: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    strategies_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    fixtures_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    round_range: Mapped[str | None] = mapped_column(String(16), nullable=True)
    recommended_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommendation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_tradeoff: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase: Mapped[str] = mapped_column(String(64), nullable=False, default="predictive_numeric", server_default="predictive_numeric")
    betting_phase_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    simulator_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    pattern_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    audit_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    competition: Mapped[Competition] = relationship("Competition")
    fixture_predictions: Mapped[list[PredictiveFixturePrediction]] = relationship(
        "PredictiveFixturePrediction",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    pattern_insights: Mapped[list[PredictivePatternInsight]] = relationship(
        "PredictivePatternInsight",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list[PredictiveFixtureNote]] = relationship(
        "PredictiveFixtureNote",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    ai_insights: Mapped[list[PredictiveAiInsight]] = relationship(
        "PredictiveAiInsight",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class PredictiveFixturePrediction(Base):
    __tablename__ = "predictive_fixture_predictions"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "fixture_id",
            "strategy_key",
            name="uq_predictive_fixture_predictions_run_fixture_strategy",
        ),
        Index("ix_predictive_fixture_predictions_run_round", "run_id", "round_number"),
        Index("ix_predictive_fixture_predictions_run_strategy", "run_id", "strategy_key"),
        Index("ix_predictive_fixture_predictions_run_abs_error", "run_id", "abs_error"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("predictive_simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    home_team_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    away_team_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    predicted_total_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_total_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[float | None] = mapped_column(Float, nullable=True)
    abs_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actual_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actual_bucket_dynamic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    win_quality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_codes_json: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    probable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    boost_applied: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_total_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    run: Mapped[PredictiveSimulationRun] = relationship("PredictiveSimulationRun", back_populates="fixture_predictions")


class PredictivePatternInsight(Base):
    __tablename__ = "predictive_pattern_insights"
    __table_args__ = (Index("ix_predictive_pattern_insights_run_type", "run_id", "insight_type"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("predictive_simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    insight_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info", server_default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[PredictiveSimulationRun] = relationship("PredictiveSimulationRun", back_populates="pattern_insights")


class PredictiveFixtureNote(Base, TimestampMixin):
    __tablename__ = "predictive_fixture_notes"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "fixture_id",
            "strategy_key",
            name="uq_predictive_fixture_notes_run_fixture_strategy",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("predictive_simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[PredictiveSimulationRun] = relationship("PredictiveSimulationRun", back_populates="notes")


class PredictiveAiInsight(Base):
    __tablename__ = "predictive_ai_insights"
    __table_args__ = (
        Index("ix_predictive_ai_insights_run_type_created", "run_id", "analysis_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("predictive_simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_type: Mapped[str] = mapped_column(String(64), nullable=False, default="legacy_generic")
    fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    strategy_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    output_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[PredictiveSimulationRun] = relationship("PredictiveSimulationRun", back_populates="ai_insights")
