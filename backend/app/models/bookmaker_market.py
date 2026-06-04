"""Catalogo mercati odds normalizzati (discovery)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class BookmakerMarket(Base, TimestampMixin):
    __tablename__ = "bookmaker_markets"
    __table_args__ = (
        UniqueConstraint(
            "provider_source",
            "provider_market_id",
            name="uq_bookmaker_markets_provider_market",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_market_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    market_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    market_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_market: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
