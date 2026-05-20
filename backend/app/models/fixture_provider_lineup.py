from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.fixture_provider_lineup_player import FixtureProviderLineupPlayer
    from app.models.fixture_missing_player import FixtureMissingPlayer


class FixtureProviderLineup(Base, TimestampMixin):
    __tablename__ = "fixture_provider_lineups"
    __table_args__ = (
        UniqueConstraint("fixture_id", "provider_name", name="uq_fixture_provider_lineups_fixture_provider"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, default="sportapi")
    provider_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    home_formation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    away_formation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="provider_lineups")
    lineup_players = relationship(
        "FixtureProviderLineupPlayer",
        back_populates="provider_lineup",
        cascade="all, delete-orphan",
    )
