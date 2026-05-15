"""Anagrafica minima giocatore (API player id stabile)."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PlayerRegistry(Base, TimestampMixin):
    __tablename__ = "player_registry"
    __table_args__ = (UniqueConstraint("api_player_id", name="uq_player_registry_api_player_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    api_player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    team_season_links = relationship("PlayerTeamSeason", back_populates="registry")
    match_stats = relationship("PlayerMatchStat", back_populates="registry")
    season_profiles = relationship("PlayerSeasonProfile", back_populates="registry")
