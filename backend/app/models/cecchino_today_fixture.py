"""Snapshot partita Cecchino Today (discovery giornaliera)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

ELIGIBILITY_ELIGIBLE = "eligible"
ELIGIBILITY_DISCOVERED = "discovered"
ELIGIBILITY_EXCLUDED_COMPETITION = "excluded_competition_type"
ELIGIBILITY_EXCLUDED_WOMEN = "excluded_women"
ELIGIBILITY_EXCLUDED_CUP = "excluded_cup"
ELIGIBILITY_EXCLUDED_FRIENDLY = "excluded_friendly"
ELIGIBILITY_EXCLUDED_YOUTH = "excluded_youth"
ELIGIBILITY_EXCLUDED_STARTED = "excluded_started"
ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER = "excluded_missing_bookmaker"
ELIGIBILITY_EXCLUDED_MISSING_1X2 = "excluded_missing_1x2_market"
ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS = "excluded_insufficient_stats"
ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO = "excluded_missing_picchetto"
ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY = "excluded_zero_probability"
ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE = "excluded_cecchino_not_calculable"
ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE = "excluded_kpi_not_calculable"
ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED = "excluded_leakage_failed"
ELIGIBILITY_EXCLUDED_MAPPING = "excluded_mapping_error"
ELIGIBILITY_ERROR = "error"

PROVIDER_API_FOOTBALL = "api_football"

MATCH_UPCOMING = "upcoming"
MATCH_LIVE = "live"
MATCH_FINISHED = "finished"
MATCH_POSTPONED = "postponed"
MATCH_CANCELLED = "cancelled"
MATCH_UNKNOWN = "unknown"


class CecchinoTodayFixture(Base, TimestampMixin):
    __tablename__ = "cecchino_today_fixtures"
    __table_args__ = (
        UniqueConstraint(
            "scan_date",
            "provider_source",
            "provider_fixture_id",
            name="uq_cecchino_today_scan_provider_fixture",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    provider_source: Mapped[str] = mapped_column(String(32), nullable=False, default=PROVIDER_API_FOOTBALL)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    local_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    competition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    provider_league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fixture_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    match_display_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_flag_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    league_logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    home_team_logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    away_team_logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    goals_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_fulltime_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_fulltime_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eligibility_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    eligibility_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    bookmaker_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stats_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cecchino_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    odds_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    stats_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cecchino_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    kpi_panel_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_fixture_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    blocking_reasons_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    odds_check_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    odds_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    negative_cache_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
