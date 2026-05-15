"""Rosa per stagione di calendario e lega (api_team denormalizzato)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PlayerTeamSeason(Base, TimestampMixin):
    __tablename__ = "player_team_seasons"
    __table_args__ = (
        UniqueConstraint(
            "season",
            "league_id",
            "api_team_id",
            "api_player_id",
            name="uq_player_team_seasons_season_league_api_team_player",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("player_registry.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    league = relationship("League", foreign_keys=[league_id])
    team = relationship("Team", back_populates="player_team_seasons")
    registry = relationship("PlayerRegistry", back_populates="team_season_links")
