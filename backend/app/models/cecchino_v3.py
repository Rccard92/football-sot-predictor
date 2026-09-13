"""Tabelle Cecchino V3 (Fase 1: specialista Forza). Separate da tutte le
tabelle V2: la V3 legge la V2 solo per il confronto, non la modifica."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
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

V3_STATUS_PENDING = "pending"
V3_STATUS_RUNNING = "running"
V3_STATUS_COMPLETED = "completed"
V3_STATUS_FAILED = "failed"
V3_STATUS_CANCELLED = "cancelled"
V3_ACTIVE_STATUSES = (V3_STATUS_PENDING, V3_STATUS_RUNNING)


class CecchinoV3Run(Base, TimestampMixin):
    __tablename__ = "cecchino_v3_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=V3_STATUS_PENDING)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # regole e griglie in vigore al momento del lancio
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CecchinoV3MatchPrediction(Base, TimestampMixin):
    __tablename__ = "cecchino_v3_match_predictions"
    __table_args__ = (
        UniqueConstraint("run_id", "lab_match_id", name="uq_cecchino_v3_match_pred_run_match"),
        Index("ix_cecchino_v3_match_pred_run_season", "run_id", "season_label"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"), nullable=False
    )
    lab_match_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    competition_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_group: Mapped[str] = mapped_column(String(64), nullable=False)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team: Mapped[str] = mapped_column(String(128), nullable=False)

    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    eval_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    home_played: Mapped[int] = mapped_column(Integer, nullable=False)
    away_played: Mapped[int] = mapped_column(Integer, nullable=False)
    home_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    away_remaining: Mapped[int] = mapped_column(Integer, nullable=False)

    lambda_home: Mapped[Decimal] = mapped_column(Numeric(8, 5), nullable=False)
    lambda_away: Mapped[Decimal] = mapped_column(Numeric(8, 5), nullable=False)
    rho: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    ht_share: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    home_evidence: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)
    away_evidence: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)
    hyper_xi: Mapped[Decimal] = mapped_column(Numeric(8, 5), nullable=False)
    hyper_sigma: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    # opinioni dei singoli specialisti e pesi dell'orchestratore (dalla Fase 2)
    specialists_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # esito reale: scritto dopo la previsione, usato solo per la valutazione
    ft_home_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    ft_away_goals: Mapped[int] = mapped_column(Integer, nullable=False)


class CecchinoV3MarketPrediction(Base):
    __tablename__ = "cecchino_v3_market_predictions"
    __table_args__ = (
        Index("ix_cecchino_v3_market_pred_run_market", "run_id", "market_key"),
        Index("ix_cecchino_v3_market_pred_match", "match_prediction_id"),
        Index("ix_cecchino_v3_market_pred_run_lab_market", "run_id", "lab_match_id", "market_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"), nullable=False
    )
    match_prediction_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_v3_match_predictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    lab_match_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    market_key: Mapped[str] = mapped_column(String(32), nullable=False)
    probability: Mapped[Decimal] = mapped_column(Numeric(9, 7), nullable=False)
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class CecchinoV3IndexRun(Base, TimestampMixin):
    """Calcolo degli indici a 360 gradi a partire da un calcolo V3 di riferimento."""

    __tablename__ = "cecchino_v3_index_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"), nullable=False
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=V3_STATUS_PENDING)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CecchinoV3MatchIndex(Base):
    __tablename__ = "cecchino_v3_match_indices"
    __table_args__ = (
        UniqueConstraint("index_run_id", "lab_match_id", name="uq_cecchino_v3_match_index_run_match"),
        Index("ix_cecchino_v3_match_index_run_comp_season", "index_run_id", "competition_name", "season_label"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    index_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_v3_index_runs.id", ondelete="CASCADE"), nullable=False
    )
    lab_match_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    competition_name: Mapped[str] = mapped_column(String(128), nullable=False)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team: Mapped[str] = mapped_column(String(128), nullable=False)
    reliability: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    reliability_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    equilibrio_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pareggio_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    intensita_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    indices_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class CecchinoV3EvaluatorRun(Base, TimestampMixin):
    """Calcolo del valutatore di mercato (Passo 3) sul modello di riferimento."""

    __tablename__ = "cecchino_v3_evaluator_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_v3_runs.id", ondelete="CASCADE"), nullable=False
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=V3_STATUS_PENDING)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CecchinoV3EvaluatorPlay(Base):
    __tablename__ = "cecchino_v3_evaluator_plays"
    __table_args__ = (
        Index("ix_cecchino_v3_eval_play_run_strategy_season", "evaluator_run_id", "strategy", "season_label"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluator_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cecchino_v3_evaluator_runs.id", ondelete="CASCADE"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    lab_match_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False)
    match_date: Mapped[date] = mapped_column(Date, nullable=False)
    competition_name: Mapped[str] = mapped_column(String(128), nullable=False)
    home_team: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team: Mapped[str] = mapped_column(String(128), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    market_key: Mapped[str] = mapped_column(String(32), nullable=False)
    odds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    p_v3: Mapped[Decimal] = mapped_column(Numeric(9, 7), nullable=False)
    p_book: Mapped[Decimal] = mapped_column(Numeric(9, 7), nullable=False)
    p_eval: Mapped[Decimal | None] = mapped_column(Numeric(9, 7), nullable=True)
    edge: Mapped[Decimal] = mapped_column(Numeric(9, 5), nullable=False)
    won: Mapped[bool] = mapped_column(Boolean, nullable=False)
    profit: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)
