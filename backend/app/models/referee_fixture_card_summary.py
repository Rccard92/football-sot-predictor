"""Cache cartellini per fixture arbitrate (discovery arbitri)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

CARD_SOURCE_EVENTS = "events"
CARD_SOURCE_STATISTICS = "statistics"
CARD_SOURCE_DB_TEAM_STATS = "db_team_stats"


class RefereeFixtureCardSummary(Base, TimestampMixin):
    __tablename__ = "referee_fixture_card_summaries"
    __table_args__ = (UniqueConstraint("api_fixture_id", name="uq_referee_fixture_card_summaries_api_fixture_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    api_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    fixture_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    referee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("referees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    league_api_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    home_team_api_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away_team_api_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    total_yellow: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_red: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_yellow: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_red: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_yellow: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_red: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    referee = relationship("Referee", back_populates="fixture_card_summaries")
    fixture = relationship("Fixture")
