from __future__ import annotations

from pydantic import BaseModel, Field


class CompetitionRead(BaseModel):
    id: int
    key: str
    name: str
    country: str | None = None
    provider: str
    provider_league_id: int
    season: int
    timezone: str | None = None
    is_active: bool
    is_primary: bool
    pre_match_cron_enabled: bool
    status: str | None = None
    league_id: int | None = None
    season_id: int | None = None

    model_config = {"from_attributes": True}


class CompetitionDiscoverBody(BaseModel):
    country: str = ""
    name_query: str = ""
    season: int


class CompetitionDiscoverCandidate(BaseModel):
    provider_league_id: int
    name: str
    country: str | None = None
    season: int
    logo: str | None = None
    season_current: bool | None = None
    raw_payload: dict | None = None


class CompetitionDiscoverResponse(BaseModel):
    candidates: list[CompetitionDiscoverCandidate]
    other_candidates: list[CompetitionDiscoverCandidate] = []
    ambiguous: bool
    message: str | None = None
    api_query: str | None = None


class CompetitionCreateBody(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    country: str | None = None
    provider: str = "api_sports"
    provider_league_id: int
    season: int
    timezone: str | None = None
    is_active: bool = True
    is_primary: bool = False
    pre_match_cron_enabled: bool = False
    status: str | None = None
    raw_payload: dict | None = None


class CompetitionPatchBody(BaseModel):
    is_active: bool | None = None
    is_primary: bool | None = None
    pre_match_cron_enabled: bool | None = None
    status: str | None = None
    timezone: str | None = None


class IngestDryRunBody(BaseModel):
    dry_run: bool = False
