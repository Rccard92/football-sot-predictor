"""Persistenza dataset empirico Balance v5 — Fase 2/3 Step 2A."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

EVAL_PENDING = "pending"
EVAL_SETTLED = "settled"
EVAL_NOT_EVALUABLE = "not_evaluable"
EVAL_RESULT_MISSING = "result_missing"
EVAL_CANCELLED = "cancelled"
EVAL_POSTPONED = "postponed"

OUTCOME_HOME = "HOME"
OUTCOME_DRAW = "DRAW"
OUTCOME_AWAY = "AWAY"


class CecchinoBalanceV5Evaluation(Base, TimestampMixin):
    __tablename__ = "cecchino_balance_v5_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "today_fixture_id",
            "balance_version",
            "snapshot_hash",
            name="uq_balance_v5_eval_fixture_version_hash",
        ),
    )

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

    empirical_dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    balance_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_mode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_cohort: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_snapshot_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pre_match_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    book_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    warning_codes: Mapped[str | None] = mapped_column(Text, nullable=True)

    f36_index: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    f36_class: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    dominance_index: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    dominance_class: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dominance_selection: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    draw_credibility_index: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    draw_credibility_class: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    gap_index: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    gap_class: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    prob_1_norm: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_x_norm: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_2_norm: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    book_prob_1: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    book_prob_x: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    book_prob_2: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    evaluation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EVAL_PENDING, index=True
    )
    evaluation_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ft_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ft_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome_1x2: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_draw: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    total_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    absolute_goal_difference: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dominance_selection_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    promotion_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
