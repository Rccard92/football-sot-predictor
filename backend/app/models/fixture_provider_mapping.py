from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.competition_scoped import CompetitionScopedMixin
from app.models.mixins import TimestampMixin

PROVIDER_SPORTAPI = "sportapi"


class FixtureProviderMapping(Base, TimestampMixin, CompetitionScopedMixin):
    __tablename__ = "fixture_provider_mappings"
    __table_args__ = (
        UniqueConstraint("fixture_id", "provider_name", name="uq_fixture_provider_mappings_fixture_provider"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, default=PROVIDER_SPORTAPI)
    provider_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_unique_tournament_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_season_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_home_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_away_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="provider_mappings")
