from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class StandingsSnapshot(Base, TimestampMixin):
    __tablename__ = "standings_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    entries = relationship(
        "StandingEntry",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class StandingEntry(Base, TimestampMixin):
    __tablename__ = "standing_entries"
    __table_args__ = (UniqueConstraint("snapshot_id", "team_id", name="uq_standing_entries_snapshot_team"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("standings_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_diff: Mapped[int | None] = mapped_column(Integer, nullable=True)
    played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    win: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lose: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_for: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_against: Mapped[int | None] = mapped_column(Integer, nullable=True)
    form: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    snapshot = relationship("StandingsSnapshot", back_populates="entries")
    team = relationship("Team")
