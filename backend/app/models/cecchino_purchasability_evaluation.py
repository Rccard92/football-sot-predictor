"""Persistenza valutazioni prospettiche Acquistabilità — Fase 5/5."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

SOURCE_PROSPECTIVE = "prospective_persisted"
SOURCE_LEGACY_BACKFILL = "legacy_persisted_backfill"
SOURCE_LEGACY_DERIVED = "legacy_derived_diagnostic"

EVAL_PENDING = "pending"
EVAL_WON = "won"
EVAL_LOST = "lost"
EVAL_NOT_EVALUABLE = "not_evaluable"
EVAL_RESULT_MISSING = "result_missing"

DEFAULT_STAKE_UNITS = Decimal("1")


class CecchinoPurchasabilityEvaluation(Base, TimestampMixin):
    __tablename__ = "cecchino_purchasability_evaluations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    today_fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_today_fixtures.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    local_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    competition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    scan_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    snapshot_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_snapshot_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snapshot_timestamp_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    snapshot_before_kickoff: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_cohort: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    candidate_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String(128), nullable=True)

    market_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selection: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calculation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calculation_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purchasability_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    raw_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    purchasability_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phase_1_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    phase_2_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    reading: Mapped[str | None] = mapped_column(Text, nullable=True)

    quota_book: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    quota_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    fair_book_probability: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    rating_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_acquisto: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    evaluation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EVAL_PENDING, index=True
    )
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

    promotion_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
