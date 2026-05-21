"""Snapshot audit discovery quote (API-Sports / SportAPI) — non usato dal modello."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PROVIDER_API_SPORTS = "api_sports"
PROVIDER_SPORTAPI = "sportapi"


class OddsDiscoverySnapshot(Base):
    __tablename__ = "odds_discovery_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    api_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sportapi_event_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sportapi_provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    markets_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bookmakers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    normalized_payload: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
