from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.competition_scoped import CompetitionScopedMixin
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.fixture_lineup_player import FixtureLineupPlayer


class FixtureLineup(Base, TimestampMixin, CompetitionScopedMixin):
    __tablename__ = "fixture_lineups"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "team_id",
            name="uq_fixture_lineups_fixture_team",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    formation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    coach_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_official: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="api_football_fixtures_lineups",
    )
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_xi: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    substitutes: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    lineup_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="lineups")
    team = relationship("Team", back_populates="fixture_lineups")
    lineup_players = relationship(
        "FixtureLineupPlayer",
        back_populates="fixture_lineup",
        cascade="all, delete-orphan",
    )
