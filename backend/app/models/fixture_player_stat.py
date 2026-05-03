from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class FixturePlayerStat(Base, TimestampMixin):
    __tablename__ = "fixture_player_stats"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "player_id",
            name="uq_fixture_player_stats_fixture_player",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="player_stats")
    player = relationship("Player", back_populates="fixture_stats")
    team = relationship("Team", back_populates="fixture_player_stats")
