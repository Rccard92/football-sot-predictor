"""Storico impatto pre/post refresh formazioni SportAPI su predizioni v2.0."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

PROVIDER_SPORTAPI_DEFAULT = "sportapi"


class FixtureLineupRefreshImpact(Base):
    __tablename__ = "fixture_lineup_refresh_impacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False, default=PROVIDER_SPORTAPI_DEFAULT)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    delta_home_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_away_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_total_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction_home: Mapped[str | None] = mapped_column(String(8), nullable=True)
    direction_away: Mapped[str | None] = mapped_column(String(8), nullable=True)
    direction_total: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reasons: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    main_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    fixture = relationship("Fixture", back_populates="lineup_refresh_impacts")
