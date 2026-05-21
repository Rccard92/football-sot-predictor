"""Pick SOT tracciati per monitoraggio live/finale (manuale o auto pre-match)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

SOURCE_MANUAL = "manual"
SOURCE_AUTO_PRE_MATCH = "auto_pre_match"

PICK_TYPE_STATISTICAL = "statistical"
PICK_TYPE_CAUTIOUS = "cautious"

STATUS_PENDING = "pending"
STATUS_LIVE = "live"
STATUS_WON = "won"
STATUS_LOST = "lost"
STATUS_VOID = "void"
STATUS_UNAVAILABLE = "unavailable"


class TrackedBettingPick(Base, TimestampMixin):
    __tablename__ = "tracked_betting_picks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(64), nullable=False)
    market_label: Mapped[str] = mapped_column(String(128), nullable=False)
    pick_type: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_pick: Mapped[str | None] = mapped_column(String(128), nullable=True)
    line_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_home_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_away_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_total_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lineup_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    lineup_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prediction_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING)
    result_home_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_away_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_total_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    fixture_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elapsed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_prediction_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_betting_advice_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="tracked_betting_picks")
