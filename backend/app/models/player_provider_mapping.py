"""Mapping giocatore SportAPI ↔ API-Football (conservativo, audit/debug)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PlayerProviderMapping(Base, TimestampMixin):
    __tablename__ = "player_provider_mappings"
    __table_args__ = (
        UniqueConstraint(
            "sportapi_player_id",
            "api_sports_team_id",
            "season",
            name="uq_player_provider_mappings_sportapi_team_season",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    api_sports_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sportapi_player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    player_name_api_sports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    player_name_sportapi: Mapped[str] = mapped_column(String(255), nullable=False)
    api_sports_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sportapi_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    league_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("leagues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    season: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
