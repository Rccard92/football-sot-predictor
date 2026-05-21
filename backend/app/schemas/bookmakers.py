"""Schemi admin bookmakers / odds discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SportApiOddsDiscoveryBody(BaseModel):
    fixture_id: int | None = None
    api_fixture_id: int | None = None
    sportapi_event_id: int | None = None
    provider_id: int = Field(default=1, ge=1)
    save_snapshot: bool = True


class SportApiOddsTestEventBody(BaseModel):
    sportapi_event_id: int = Field(..., ge=1)
    provider_slug: str = Field(default="sisal-italy-affiliate", min_length=1)
    provider_id: int | None = Field(default=None, ge=1)
    save_snapshot: bool = False
    fixture_id: int | None = None
    api_fixture_id: int | None = None


class SportApiNextRound1x2Body(BaseModel):
    provider_slug: str = Field(default="sisal-italy-affiliate", min_length=1)
    force: bool = False
    season_year: int | None = None
