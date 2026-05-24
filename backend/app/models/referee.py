"""Arbitri da API-Sports (discovery, non usati nel modello SOT v2.0)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

PROVIDER_API_SPORTS = "api_sports"


class Referee(Base, TimestampMixin):
    __tablename__ = "referees"
    __table_args__ = (
        UniqueConstraint("provider", "normalized_name", name="uq_referees_provider_normalized_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default=PROVIDER_API_SPORTS)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture_assignments = relationship("FixtureReferee", back_populates="referee")
    season_profiles = relationship("RefereeSeasonProfile", back_populates="referee")
    fixture_card_summaries = relationship("RefereeFixtureCardSummary", back_populates="referee")
