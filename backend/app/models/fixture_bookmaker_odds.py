"""Quote bookmaker per fixture (store unificato discovery)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class FixtureBookmakerOdds(Base, TimestampMixin):
    __tablename__ = "fixture_bookmaker_odds"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "fixture_id",
            "provider_source",
            "provider_bookmaker_id",
            "normalized_market",
            name="uq_fixture_bookmaker_odds_scope",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_bookmaker_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bookmaker_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_market_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_market: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    home_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    odds_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
