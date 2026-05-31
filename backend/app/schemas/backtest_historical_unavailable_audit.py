"""Schemi audit indisponibili storici read-only (Step JK.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HistoricalUnavailableAuditPlayerSample(BaseModel):
    player_name: str
    absence_group: str
    side: str


class HistoricalUnavailableAuditFixtureSample(BaseModel):
    fixture_id: int
    round: str | None = None
    home_team: str
    away_team: str
    home_unavailable_count: int = 0
    away_unavailable_count: int = 0
    home_injured_count: int = 0
    away_injured_count: int = 0
    home_suspended_count: int = 0
    away_suspended_count: int = 0
    source_paths: list[str] = Field(default_factory=list)
    source_paths_used_for_counts: list[str] = Field(default_factory=list)
    source_paths_detected_diagnostic: list[str] = Field(default_factory=list)
    players: list[HistoricalUnavailableAuditPlayerSample] = Field(default_factory=list)


class HistoricalUnavailableAuditResponse(BaseModel):
    status: str = "ok"
    preview_only: bool = True
    db_writes: bool = False
    competition_id: int
    competition_name: str
    round_number: int | None = None
    limit: int
    offset: int
    fixtures_scanned: int = 0
    fixtures_with_unavailable: int = 0
    fixtures_with_injured: int = 0
    fixtures_with_suspended: int = 0
    total_unavailable_players: int = 0
    total_injured_players: int = 0
    total_suspended_players: int = 0
    sample_fixtures_with_unavailable: list[HistoricalUnavailableAuditFixtureSample] = Field(
        default_factory=list,
    )
    source_paths_found: list[str] = Field(default_factory=list)
    source_paths_used_for_counts: list[str] = Field(default_factory=list)
    source_paths_detected_diagnostic: list[str] = Field(default_factory=list)
    raw_json_keys_detected: list[str] = Field(default_factory=list)
    storage_checked: list[str] = Field(default_factory=list)
    verdict: str = "unavailable_not_found_in_current_storage"
