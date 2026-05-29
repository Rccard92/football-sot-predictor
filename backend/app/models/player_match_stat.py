"""Statistiche giocatore per singola partita (layer Player DB)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.competition_scoped import CompetitionScopedMixin
from app.models.mixins import TimestampMixin


class PlayerMatchStat(Base, TimestampMixin, CompetitionScopedMixin):
    __tablename__ = "player_match_stats"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "api_team_id",
            "api_player_id",
            name="uq_player_match_stats_fixture_api_team_player",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
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

    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    substitute: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    shots_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_assists: Mapped[int | None] = mapped_column(Integer, nullable=True)

    passes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_key: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    dribbles_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dribbles_success: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fouls_drawn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_committed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cards_yellow: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cards_red: Mapped[int | None] = mapped_column(Integer, nullable=True)

    penalty_scored: Mapped[int | None] = mapped_column(Integer, nullable=True)
    penalty_missed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    penalty_won: Mapped[int | None] = mapped_column(Integer, nullable=True)

    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", foreign_keys=[fixture_id])
    league = relationship("League", foreign_keys=[league_id])
    team = relationship("Team", foreign_keys=[team_id])
    registry = relationship("PlayerRegistry", back_populates="match_stats")
