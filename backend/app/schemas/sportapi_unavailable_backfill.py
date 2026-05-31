"""Schemi backfill unavailable SportAPI (Step K.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SportApiUnavailableBackfillRequest(BaseModel):
    round_number: int | None = Field(default=None, ge=1)
    fixture_ids: list[int] | None = None
    dry_run: bool = True
    force_refresh: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    auto_confirm_mapping: bool = False


class SportApiUnavailableBackfillFixtureSample(BaseModel):
    fixture_id: int
    round: str | None = None
    home_team: str
    away_team: str
    unavailable_found: int = 0
    would_write: int = 0
    written: int = 0
    mapping_status: str
    data_source: str | None = None
    detected_paths: list[str] = Field(default_factory=list)


class SportApiUnavailableBackfillResponse(BaseModel):
    status: str = "ok"
    dry_run: bool = True
    competition_id: int
    competition_name: str
    round_number: int | None = None
    fixtures_processed: int = 0
    fixtures_with_unavailable_from_provider: int = 0
    total_unavailable_found: int = 0
    total_written: int = 0
    mapping_missing_count: int = 0
    fetch_errors: int = 0
    samples: list[SportApiUnavailableBackfillFixtureSample] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
