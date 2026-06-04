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


class SportApiMarketsDiscoveryBody(BaseModel):
    sportapi_event_id: int = Field(..., ge=1)
    provider_slug: str = Field(default="sisal-italy-affiliate", min_length=1)
    provider_id: int | None = Field(default=None, ge=1)


class SportApiMarketMappingBody(BaseModel):
    provider_slug: str = Field(default="sisal-italy-affiliate", min_length=1)
    raw_market_name: str = Field(..., min_length=1)
    normalized_market_key: str = Field(..., min_length=1)
    provider_id_used: int | None = Field(default=None, ge=1)
    raw_market_id: str | None = None
    confidence: str = Field(default="manual", min_length=1)
    sample_raw_market: dict | None = None


class SportApiNextRoundSotBody(BaseModel):
    provider_slug: str = Field(default="sisal-italy-affiliate", min_length=1)
    season_year: int | None = None
    market_key: str = Field(default="match_total_sot", min_length=1)
    limit: int = Field(default=50, ge=1, le=100)


class SportApiScanSotProvidersBody(BaseModel):
    sportapi_event_id: int = Field(..., ge=1)
    country: str = Field(default="IT", min_length=2, max_length=8)
    max_providers: int | None = Field(default=None, ge=1, le=200)
    provider_slug: str | None = None
    save_snapshot: bool = False
    auto_sync_if_empty: bool = False
    channel: str = Field(default="app", min_length=2, max_length=16)


class SportApiProvidersSyncBody(BaseModel):
    country: str = Field(default="IT", min_length=2, max_length=8)
    channel: str = Field(default="app", min_length=2, max_length=16)


class BookmakerSyncNextRoundBody(BaseModel):
    market: str = Field(default="MATCH_WINNER_1X2", min_length=1)
    provider_source: str = Field(default="auto", min_length=1)
    bookmaker_name: str | None = None
    provider_slug: str = Field(default="sisal-italy-affiliate", min_length=1)
