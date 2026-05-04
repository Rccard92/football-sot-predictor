from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PlayerAvailabilityEvent(Base, TimestampMixin):
    __tablename__ = "player_availability_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    api_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fixture_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    season = relationship("Season", back_populates="availability_events")
    team = relationship("Team", back_populates="availability_events")
    player = relationship("Player", back_populates="availability_events")
    fixture = relationship("Fixture", back_populates="availability_events")
