from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.fixture_provider_lineup import FixtureProviderLineup


class FixtureProviderLineupPlayer(Base, TimestampMixin):
    __tablename__ = "fixture_provider_lineup_players"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "provider_name",
            "provider_player_id",
            "team_side",
            "is_substitute",
            name="uq_fixture_provider_lineup_players_natural",
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
    team_side: Mapped[str] = mapped_column(String(8), nullable=False)  # home | away
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_substitute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    provider_lineup = relationship("FixtureProviderLineup", back_populates="lineup_players")
