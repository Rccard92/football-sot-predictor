"""Persistenza storica segnali KPI (righe Pannello KPI con rating >= 50)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

KPI_EVAL_PENDING = "pending"
KPI_EVAL_WON = "won"
KPI_EVAL_LOST = "lost"
KPI_EVAL_NOT_EVALUABLE = "not_evaluable"
KPI_EVAL_RESULT_MISSING = "result_missing"

DEFAULT_STAKE_UNITS = Decimal("1")


class CecchinoKpiSignalActivation(Base, TimestampMixin):
    __tablename__ = "cecchino_kpi_signal_activations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    today_fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_today_fixtures.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    kpi_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kpi_row_key: Mapped[str] = mapped_column(String(64), nullable=False)
    selection_label: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_market: Mapped[str] = mapped_column(String(64), nullable=False)
    selection_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rating_score: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rating_bucket: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    quota_book: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quota_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    prob_book: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    prob_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    score_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    evaluation_status: Mapped[str] = mapped_column(String(32), nullable=False, default=KPI_EVAL_PENDING)
    evaluation_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_home_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_away_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_home_ht: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_away_ht: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stake_units: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=DEFAULT_STAKE_UNITS,
        server_default="1",
    )
    profit_units: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
