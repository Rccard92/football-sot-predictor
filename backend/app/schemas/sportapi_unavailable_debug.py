"""Schemi debug unavailable SportAPI (Step K.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SportApiUnavailablePlayerSample(BaseModel):
    player_name: str
    team_side: str
    status: str
    provider_player_id: int | None = None
    source_path: str
    persistable: bool = True


class SportApiUnavailableDebugResponse(BaseModel):
    status: str = "ok"
    dry_run: bool = True
    competition_id: int
    internal_fixture_id: int
    provider_fixture_id: int | None = None
    source_fixture_id: int
    mapping_status: str
    data_source: str = "live"
    home_unavailable_count: int = 0
    away_unavailable_count: int = 0
    total_unavailable_found: int = 0
    detected_paths: list[str] = Field(default_factory=list)
    raw_json_keys_detected: list[str] = Field(default_factory=list)
    sample_unavailable_players: list[SportApiUnavailablePlayerSample] = Field(default_factory=list)
    would_write_count: int = 0
    skipped_missing_provider_player_id: int = 0
    suggested_next_step: str | None = None
    warnings: list[str] = Field(default_factory=list)
