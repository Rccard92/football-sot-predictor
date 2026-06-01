"""Modelli analisi giornata persistente (Step I)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.competition import Competition
    from app.models.fixture import Fixture


class BacktestRoundAnalysis(Base):
    __tablename__ = "backtest_round_analyses"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "season_year",
            "round_number",
            "analysis_version",
            name="uq_backtest_round_analyses_comp_season_round_ver",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="historical_official_xi")
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    total_fixtures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_fixtures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_fixtures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    data_quality_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    model_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    competition: Mapped["Competition"] = relationship("Competition")
    fixture_results: Mapped[list["BacktestRoundFixtureResult"]] = relationship(
        "BacktestRoundFixtureResult",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )


class BacktestRoundFixtureResult(Base):
    __tablename__ = "backtest_round_fixture_results"
    __table_args__ = (
        UniqueConstraint("analysis_id", "fixture_id", name="uq_backtest_round_fixture_results_analysis_fixture"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("backtest_round_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_team_name: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_home_sot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_away_sot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_total_sot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    models_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    explanation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok", server_default="ok")
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    analysis: Mapped["BacktestRoundAnalysis"] = relationship("BacktestRoundAnalysis", back_populates="fixture_results")
    fixture: Mapped["Fixture"] = relationship("Fixture")
