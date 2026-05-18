"""Indisponibilità giocatore (infortuni/squalifiche) — stage 8A audit."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.fixture import Fixture
    from app.models.player_registry import PlayerRegistry
    from app.models.team import Team

SCOPE_FIXTURE_LEVEL = "fixture_level"
SCOPE_TEAM_LEVEL = "team_level"
SCOPE_SEASON_LEVEL = "season_level"
SCOPE_MANUAL_FIXTURE_LEVEL = "manual_fixture_level"
SCOPE_MANUAL_TEAM_LEVEL = "manual_team_level"

RECORD_SCOPES = (
    SCOPE_FIXTURE_LEVEL,
    SCOPE_TEAM_LEVEL,
    SCOPE_SEASON_LEVEL,
    SCOPE_MANUAL_FIXTURE_LEVEL,
    SCOPE_MANUAL_TEAM_LEVEL,
)


class PlayerAvailability(Base, TimestampMixin):
    __tablename__ = "player_availability"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    league_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    fixture_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    team_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("player_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)

    availability_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    availability_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fixture_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    record_scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture")
    team = relationship("Team")
    registry: Mapped["PlayerRegistry | None"] = relationship("PlayerRegistry")
