"""Giocatori in formazione ufficiale per fixture/squadra."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.competition_scoped import CompetitionScopedMixin
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.fixture_lineup import FixtureLineup
    from app.models.player_registry import PlayerRegistry


class FixtureLineupPlayer(Base, TimestampMixin, CompetitionScopedMixin):
    __tablename__ = "fixture_lineup_players"
    __table_args__ = (
        UniqueConstraint(
            "fixture_lineup_id",
            "api_player_id",
            "is_starter",
            name="uq_fixture_lineup_players_lineup_player_starter",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_lineup_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixture_lineups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    league_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("player_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(16), nullable=True)
    grid: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_substitute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fixture_lineup: Mapped["FixtureLineup"] = relationship(
        "FixtureLineup",
        back_populates="lineup_players",
    )
    registry: Mapped["PlayerRegistry | None"] = relationship("PlayerRegistry")
