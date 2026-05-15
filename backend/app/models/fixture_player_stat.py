from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
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
    api_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    captain: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    substitute: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    shots_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assists: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_key: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    tackles_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tackles_blocks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interceptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duels_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duels_won: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dribbles_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dribbles_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_drawn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_committed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    penalty_scored: Mapped[int | None] = mapped_column(Integer, nullable=True)
    penalty_missed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    penalty_won: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="player_stats")
    player = relationship("Player", back_populates="fixture_stats")
    team = relationship("Team", back_populates="fixture_player_stats")
