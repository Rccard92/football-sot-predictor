"""Schemi admin bookmakers / odds discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SportApiOddsDiscoveryBody(BaseModel):
    fixture_id: int | None = None
    api_fixture_id: int | None = None
    sportapi_event_id: int | None = None
    provider_id: int = Field(default=1, ge=1)
    save_snapshot: bool = True
