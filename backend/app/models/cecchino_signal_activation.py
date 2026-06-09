"""Persistenza storica segnali SI matrice Cecchino."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

EVAL_PENDING = "pending"
EVAL_WON = "won"
EVAL_LOST = "lost"
EVAL_VOID = "void"
EVAL_NOT_EVALUABLE = "not_evaluable"
EVAL_RESULT_MISSING = "result_missing"

PERIOD_FT = "FT"
PERIOD_HT = "HT"
PERIOD_UNKNOWN = "UNKNOWN"


class CecchinoSignalActivation(Base, TimestampMixin):
    __tablename__ = "cecchino_signal_activations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    today_fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_today_fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    local_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_source: Mapped[str] = mapped_column(String(32), nullable=False, default="api_football")
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    model_key: Mapped[str] = mapped_column(String(8), nullable=False, default="F", server_default="F", index=True)
    model_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    weights_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weights_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    signal_group: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_label: Mapped[str] = mapped_column(String(128), nullable=False)
    source_column: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_value: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_signal_value: Mapped[str | None] = mapped_column(String(8), nullable=True)

    f32: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    f33: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    f34: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    f35: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    f36: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    target_market_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_market_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_period: Mapped[str] = mapped_column(String(16), nullable=False, default=PERIOD_UNKNOWN)

    evaluation_status: Mapped[str] = mapped_column(String(32), nullable=False, default=EVAL_PENDING)
    evaluation_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ht_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ft_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ft_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    quota_book: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    quota_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    prob_book: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    prob_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
