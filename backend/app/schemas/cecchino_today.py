"""Schemi API Cecchino Today."""

from __future__ import annotations

from datetime import date as DateType
from typing import Any

from pydantic import BaseModel, Field

from app.services.cecchino.cecchino_today_constants import DEFAULT_TODAY_TIMEZONE


class CecchinoTodayScanBody(BaseModel):
    scan_date: DateType | None = None
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)


class CecchinoTodayScanDayBody(BaseModel):
    date: DateType
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)
    force_rescan: bool = False


class CecchinoTodayUpdateResultsBody(BaseModel):
    target_date: DateType | None = Field(default=None, alias="date")
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)

    model_config = {"populate_by_name": True}


class CecchinoTodayCleanupBody(BaseModel):
    retention_days: int = Field(default=7, ge=1, le=90)
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)


class CecchinoTodayDay(BaseModel):
    date: str
    label: str
    is_today: bool = False
    is_future: bool = False
    is_scanned: bool = False
    eligible_count: int = 0
    excluded_count: int = 0
    upcoming_count: int = 0
    live_count: int = 0
    finished_count: int = 0
    last_scan_at: str | None = None
    scan_state: str = "not_scanned"
    status: str = "pending"


class CecchinoTodayDaysResponse(BaseModel):
    status: str
    version: str
    timezone: str
    today: str
    tomorrow: str
    selected_default: str
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


class CecchinoTodayFixtureStatusDebug(BaseModel):
    fixture_status_at_scan: str
    elapsed_at_scan: int | None = None
    message: str | None = None


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
    fixture_status_debug: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
