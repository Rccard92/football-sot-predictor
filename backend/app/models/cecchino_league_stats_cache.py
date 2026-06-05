"""Cache import storico lega/stagione per Cecchino Today."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoLeagueStatsCache(Base, TimestampMixin):
    __tablename__ = "cecchino_league_stats_cache"
    __table_args__ = (
        UniqueConstraint(
            "provider_league_id",
            "season",
            name="uq_cecchino_league_stats_cache_league_season",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_league_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_stats_import_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fixtures_ft_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_minimum_stats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stats_quality_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
