"""Schemi backfill mapping fixture SportAPI (Step K.3)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.sportapi_fixture_mapping_debug import (
    MatchConfidence,
    SportApiMappingCandidateBrief,
)


class SportApiFixtureMappingBackfillRequest(BaseModel):
    round_number: int | None = Field(default=None, ge=1)
    fixture_ids: list[int] | None = None
    dry_run: bool = True
    force_refresh: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SportApiFixtureMappingBackfillItem(BaseModel):
    fixture_id: int
    round: str | None = None
    home_team: str
    away_team: str
    existing_mapping: bool = False
    match_confidence: MatchConfidence = "none"
    ambiguous_high_matches: bool = False
    best_candidate: SportApiMappingCandidateBrief | None = None
    would_write_mapping: bool = False
    mapping_written: bool = False
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SportApiFixtureMappingBackfillResponse(BaseModel):
    status: str = "ok"
    dry_run: bool = True
    competition_id: int
    competition_name: str
    round_number: int | None = None
    fixtures_processed: int = 0
    existing_mappings: int = 0
    high_confidence_matches: int = 0
    medium_confidence_matches: int = 0
    low_confidence_matches: int = 0
    written_mappings: int = 0
    ambiguous_matches: int = 0
    fetch_errors: int = 0
    items: list[SportApiFixtureMappingBackfillItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
