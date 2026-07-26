"""Partite storiche normalizzate Cecchino Lab (fonte Football-Data, quote Bet365)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

ROW_QUALITY_COMPLETE = "complete"
ROW_QUALITY_PARTIAL = "partial"
ROW_QUALITY_ERROR = "error"


class CecchinoLabMatch(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_matches"
    __table_args__ = (
        Index("ix_cecchino_lab_matches_dataset_id", "dataset_id"),
        Index("ix_cecchino_lab_matches_import_id", "import_id"),
        Index("ix_cecchino_lab_matches_match_date", "match_date"),
        Index("ix_cecchino_lab_matches_row_quality_status", "row_quality_status"),
        Index("ix_cecchino_lab_matches_home_team", "home_team"),
        Index("ix_cecchino_lab_matches_away_team", "away_team"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    import_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    division_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    match_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    match_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    away_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referee: Mapped[str | None] = mapped_column(String(128), nullable=True)

    ft_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ft_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ft_result: Mapped[str | None] = mapped_column(String(1), nullable=True)
    ht_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_result: Mapped[str | None] = mapped_column(String(1), nullable=True)

    home_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)

    bet365_home: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_draw: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_away: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_over_25: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_under_25: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    asian_handicap_home_line: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    bet365_ah_home: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_ah_away: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    bet365_closing_home: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_closing_draw: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_closing_away: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_closing_over_25: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_closing_under_25: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    asian_handicap_closing_home_line: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 3), nullable=True
    )
    bet365_closing_ah_home: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    bet365_closing_ah_away: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    result_ft_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    result_ht_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    statistics_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bet365_1x2_pre_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bet365_1x2_closing_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bet365_ou25_pre_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bet365_ou25_closing_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    row_quality_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ROW_QUALITY_PARTIAL
    )
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
