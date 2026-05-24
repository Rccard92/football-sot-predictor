"""Cache profilo severità arbitro per lega/stagione."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

SAMPLE_QUALITY_LOW = "low"
SAMPLE_QUALITY_MEDIUM = "medium"
SAMPLE_QUALITY_HIGH = "high"


class RefereeSeasonProfile(Base, TimestampMixin):
    __tablename__ = "referee_season_profiles"
    __table_args__ = (
        UniqueConstraint(
            "referee_id",
            "league_id",
            "season",
            name="uq_referee_season_profiles_referee_league_season",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("referees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    league_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    matches_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_yellow_cards: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_red_cards: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_yellow_cards: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_red_cards: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    referee = relationship("Referee", back_populates="season_profiles")
