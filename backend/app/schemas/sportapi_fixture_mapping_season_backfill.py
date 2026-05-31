"""Schemi backfill mapping fixture SportAPI stagione (Step K.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.sportapi_fixture_mapping_backfill import SportApiFixtureMappingBackfillItem


class SportApiFixtureMappingSeasonBackfillRequest(BaseModel):
    dry_run: bool = True
    force_refresh: bool = False
    only_finished: bool = True
    limit: int = Field(default=400, ge=1, le=400)
    offset: int = Field(default=0, ge=0)
    round_from: int | None = Field(default=None, ge=1)
    round_to: int | None = Field(default=None, ge=1)
    sleep_between_fixtures_s: float | None = None


class SportApiFixtureMappingSeasonBackfillResponse(BaseModel):
    status: str = "ok"
    dry_run: bool = True
    competition_id: int
    competition_name: str
    fixtures_processed: int = 0
    total_candidates: int = 0
    has_more: bool = False
    existing_mappings: int = 0
    high_confidence_matches: int = 0
    medium_confidence_matches: int = 0
    low_confidence_matches: int = 0
    written_mappings: int = 0
    ambiguous_matches: int = 0
    fetch_errors: int = 0
    api_calls: int = 0
    items_sample: list[SportApiFixtureMappingBackfillItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
