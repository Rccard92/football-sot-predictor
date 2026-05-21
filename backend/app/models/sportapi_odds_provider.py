"""Provider odds SportAPI (mercato IT/app, dettaglio per slug)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

DEFAULT_PROVIDER_SLUG = "sisal-italy-affiliate"


class SportApiOddsProvider(Base, TimestampMixin):
    __tablename__ = "sportapi_odds_providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odds_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odds_from_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    odds_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    live_odds_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    live_odds_from_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    live_odds_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_bet_slip_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    working_odds_provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
