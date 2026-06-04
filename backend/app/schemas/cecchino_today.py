"""Schemi API Cecchino Today."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.services.cecchino.cecchino_today_constants import DEFAULT_TODAY_TIMEZONE


class CecchinoTodayScanBody(BaseModel):
    scan_date: date | None = None
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)


class CecchinoTodayCleanupBody(BaseModel):
    retention_days: int = Field(default=7, ge=1, le=90)
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)


class CecchinoTodayDay(BaseModel):
    date: str
    label: str
    eligible_count: int
    excluded_count: int
    last_scan_at: str | None = None
    status: str


class CecchinoTodayDaysResponse(BaseModel):
    status: str
    version: str
    timezone: str
    today: str
    tomorrow: str
    days: list[CecchinoTodayDay]


class CecchinoTodayBookmakerDebug(BaseModel):
    Bet365: str = "missing"
    Betfair: str = "missing"
    Pinnacle: str = "missing"


class CecchinoTodayStatsDebug(BaseModel):
    status: str
    home_context_sample: int = 0
    away_context_sample: int = 0
    home_total_sample: int = 0
    away_total_sample: int = 0


class CecchinoTodayCompetitionFilterDebug(BaseModel):
    allowed: bool
    reason: str | None = None


class CecchinoTodayExcludedFixture(BaseModel):
    id: int
    provider_fixture_id: int
    home_team_name: str | None = None
    away_team_name: str | None = None
    league_name: str | None = None
    country_name: str | None = None
    kickoff: str | None = None
    eligibility_status: str
    eligibility_reason: str | None = None
    bookmaker_debug: dict[str, Any] = Field(default_factory=dict)
    stats_debug: dict[str, Any] = Field(default_factory=dict)
    competition_filter_debug: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
