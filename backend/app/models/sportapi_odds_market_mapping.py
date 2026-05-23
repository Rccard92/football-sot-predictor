"""Mapping mercati odds SportAPI → chiavi normalizzate (preparazione quote SOT)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

CONFIDENCE_MANUAL = "manual"
CONFIDENCE_AUTO_HIGH = "auto_high"
CONFIDENCE_AUTO_MEDIUM = "auto_medium"
CONFIDENCE_AUTO_LOW = "auto_low"

MARKET_KEY_MATCH_TOTAL_SOT = "match_total_sot"
MARKET_KEY_HOME_TEAM_SOT = "home_team_sot"
MARKET_KEY_AWAY_TEAM_SOT = "away_team_sot"
MARKET_KEY_PLAYER_SOT = "player_sot"
MARKET_KEY_MATCH_1X2 = "match_1x2"


class SportApiOddsMarketMapping(Base, TimestampMixin):
    __tablename__ = "sportapi_odds_market_mappings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_id_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_market_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_market_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default=CONFIDENCE_MANUAL)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sample_raw_market: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
