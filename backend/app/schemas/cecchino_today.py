"""Schemi API Cecchino Today."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.services.cecchino.cecchino_today_constants import DEFAULT_TODAY_TIMEZONE


class CecchinoTodayScanBody(BaseModel):
    scan_date: date | None = None
    timezone: str = Field(default=DEFAULT_TODAY_TIMEZONE)
