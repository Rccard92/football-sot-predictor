"""Snapshot quote SportAPI per fixture (audit, non modello)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.competition_scoped import CompetitionScopedMixin

MARKET_1X2 = "1x2"


class SportApiFixtureOddsSnapshot(Base, CompetitionScopedMixin):
    __tablename__ = "sportapi_fixture_odds_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    api_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sportapi_event_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    provider_slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_id_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_key: Mapped[str] = mapped_column(String(32), nullable=False, default=MARKET_1X2)
    market_name_original: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_odd: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_odd: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_odd: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
