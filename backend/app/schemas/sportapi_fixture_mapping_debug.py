"""Schemi debug mapping fixture SportAPI (Step K.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

MatchConfidence = Literal["high", "medium", "low", "none"]


class SportApiInternalFixtureBrief(BaseModel):
    fixture_id: int
    competition_id: int
    competition_name: str
    round: str | None = None
    kickoff_at: datetime
    home_team: str
    away_team: str


class SportApiExistingMappingBrief(BaseModel):
    found: bool = False
    provider_fixture_id: int | None = None
    source: str | None = None
    confidence_score: float | None = None
    matched_by: str | None = None


class SportApiMappingCandidateBrief(BaseModel):
    provider_event_id: int
    score: float
    confidence: MatchConfidence
    home_team_name: str
    away_team_name: str
    start_timestamp: int | None = None
    round_number: int | None = None
    tournament_name: str | None = None
    breakdown: dict[str, Any] = Field(default_factory=dict)


class SportApiFixtureMappingDebugResponse(BaseModel):
    status: str = "ok"
    dry_run: bool = True
    internal_fixture: SportApiInternalFixtureBrief
    existing_mapping: SportApiExistingMappingBrief
    sportapi_candidates: list[SportApiMappingCandidateBrief] = Field(default_factory=list)
    best_candidate: SportApiMappingCandidateBrief | None = None
    match_confidence: MatchConfidence = "none"
    ambiguous_high_matches: bool = False
    would_write_mapping: bool = False
    mapping_written: bool = False
    warnings: list[str] = Field(default_factory=list)
    scheduled_events_count: int = 0
    api_calls: int = 0
