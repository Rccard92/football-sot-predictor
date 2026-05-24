"""Collegamento fixture ↔ arbitro (fonte API-Sports)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin
from app.models.referee import PROVIDER_API_SPORTS

SOURCE_API_SPORTS = PROVIDER_API_SPORTS


class FixtureReferee(Base, TimestampMixin):
    __tablename__ = "fixture_referees"
    __table_args__ = (
        UniqueConstraint("fixture_id", "source", name="uq_fixture_referees_fixture_source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    referee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("referees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    referee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default=SOURCE_API_SPORTS)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="fixture_referees")
    referee = relationship("Referee", back_populates="fixture_assignments")
