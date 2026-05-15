"""Profilo aggregato giocatore per stagione (layer Player DB)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PlayerSeasonProfile(Base, TimestampMixin):
    __tablename__ = "player_season_profiles"
    __table_args__ = (
        UniqueConstraint(
            "season",
            "league_id",
            "api_team_id",
            "api_player_id",
            name="uq_player_season_profiles_season_league_api_team_player",
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

    matches_played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    minutes_avg: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    starts_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)

    shots_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_total_per90: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    shots_on_per90: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    shot_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    goals_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assists_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_passes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_passes_per90: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    recent_minutes_last5: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    recent_shots_total_last5: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recent_shots_on_last5: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recent_rating_last5: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    team_shots_share: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    team_sot_share: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    shooting_impact_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    reliability_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    league = relationship("League", foreign_keys=[league_id])
    team = relationship("Team", foreign_keys=[team_id])
    registry = relationship("PlayerRegistry", back_populates="season_profiles")
