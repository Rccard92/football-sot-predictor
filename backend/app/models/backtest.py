"""Modelli Backtest Engine multi-mercato (Step B — DB foundation, nessun runtime)."""

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
    from app.models.season import Season
    from app.models.team import Team


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("seasons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    season_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    date_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    algorithm_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_manifest_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    git_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    competition: Mapped[Competition] = relationship("Competition")
    season: Mapped[Season | None] = relationship("Season")
    predictions: Mapped[list[BacktestPrediction]] = relationship(
        "BacktestPrediction",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    picks: Mapped[list[BacktestPick]] = relationship(
        "BacktestPick",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[list[BacktestRunMetric]] = relationship(
        "BacktestRunMetric",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class BacktestPrediction(Base):
    __tablename__ = "backtest_predictions"
    __table_args__ = (
        UniqueConstraint(
            "backtest_run_id",
            "fixture_id",
            "prediction_scope",
            name="uq_backtest_predictions_run_fixture_scope",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prediction_scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    abs_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    trace_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    feature_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[BacktestRun] = relationship("BacktestRun", back_populates="predictions")
    fixture: Mapped[Fixture] = relationship("Fixture")
    team: Mapped[Team | None] = relationship("Team")


class BacktestPick(Base):
    __tablename__ = "backtest_picks"
    __table_args__ = (
        UniqueConstraint(
            "backtest_run_id",
            "fixture_id",
            "prediction_scope",
            "bet_type",
            "line_value",
            "pick_side",
            name="uq_backtest_picks_run_fixture_scope_bet",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prediction_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bet_type: Mapped[str] = mapped_column(String(32), nullable=False)
    line_value: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    pick_side: Mapped[str] = mapped_column(String(16), nullable=False)
    predicted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    confidence_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[BacktestRun] = relationship("BacktestRun", back_populates="picks")
    fixture: Mapped[Fixture] = relationship("Fixture")
    team: Mapped[Team | None] = relationship("Team")


class BacktestRunMetric(Base):
    __tablename__ = "backtest_run_metrics"
    __table_args__ = (
        UniqueConstraint(
            "backtest_run_id",
            "metric_key",
            name="uq_backtest_run_metrics_run_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    run: Mapped[BacktestRun] = relationship("BacktestRun", back_populates="metrics")
