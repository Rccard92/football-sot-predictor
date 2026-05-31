"""Schemi backfill unavailable SportAPI stagione (Step K.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.sportapi_unavailable_backfill import SportApiUnavailableBackfillFixtureSample


class SportApiUnavailableSeasonBackfillRequest(BaseModel):
    dry_run: bool = True
    force_refresh: bool = False
    only_finished: bool = True
    limit: int = Field(default=400, ge=1, le=400)
    offset: int = Field(default=0, ge=0)
    round_from: int | None = Field(default=None, ge=1)
    round_to: int | None = Field(default=None, ge=1)
    sleep_between_fixtures_s: float | None = None


class SportApiUnavailableSeasonBackfillResponse(BaseModel):
    status: str = "ok"
    dry_run: bool = True
    competition_id: int
    competition_name: str
    fixtures_processed: int = 0
    total_candidates: int = 0
    has_more: bool = False
    fixtures_with_mapping: int = 0
    fixtures_mapping_missing: int = 0
    fixtures_with_unavailable_from_provider: int = 0
    total_unavailable_found: int = 0
    total_written: int = 0
    skipped_missing_provider_player_id: int = 0
    fetch_errors: int = 0
    api_calls: int = 0
    source_paths_found: list[str] = Field(default_factory=list)
    samples: list[SportApiUnavailableBackfillFixtureSample] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
