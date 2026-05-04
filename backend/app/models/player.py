from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class Player(Base, TimestampMixin):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("api_player_id", name="uq_players_api_player_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    api_player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    team = relationship("Team", back_populates="players")
    fixture_stats = relationship("FixturePlayerStat", back_populates="player")
    sot_profile_rows = relationship("PlayerSotProfile", back_populates="player")
    availability_events = relationship("PlayerAvailabilityEvent", back_populates="player")
