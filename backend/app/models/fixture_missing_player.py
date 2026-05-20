from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class FixtureMissingPlayer(Base, TimestampMixin):
    __tablename__ = "fixture_missing_players"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "provider_name",
            "provider_player_id",
            "team_side",
            name="uq_fixture_missing_players_natural",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_lineup_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fixture_provider_lineups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, default="sportapi")
    provider_player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    team_side: Mapped[str] = mapped_column(String(8), nullable=False)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
