"""Schemi API Historical Official XI Audit (Step G2A)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HistoricalLineupSideCoverage(BaseModel):
    has_official_xi: bool = False
    starters_count: int = 0
    bench_count: int = 0
    unavailable_count: int = 0
    injured_count: int = 0
    suspended_count: int = 0
    formation: str | None = None
    source_table: str | None = None
    source_provider: str | None = None
    source_timestamp: datetime | None = None
    is_timestamp_safe: bool = False
    source_timestamp_status: str = "missing"
    warnings: list[str] = Field(default_factory=list)


class HistoricalLineupPlayerMappingSummary(BaseModel):
    starters_with_provider_player_id: int = 0
    starters_with_internal_player_id: int = 0
    starters_matched_to_fixture_player_stats_prior: int = 0
    starters_missing_prior_stats: int = 0
    bench_with_provider_player_id: int = 0
    unavailable_with_provider_player_id: int = 0
    mapping_coverage_pct: float | None = None
    player_stats_prior_coverage_pct: float | None = None


class HistoricalLineupPlayerPriorStats(BaseModel):
    player_name: str
    provider_player_id: int | None = None
    internal_player_id: int | None = None
    api_player_id: int | None = None
    role: str | None = None
    is_starter: bool = True
    prior_minutes: int = 0
    prior_shots_total: int = 0
    prior_shots_on: int = 0
    prior_sot_per90: float | None = None
    prior_shots_per90: float | None = None
    prior_team_sot_share: float | None = None
    prior_matches_count: int = 0
    latest_player_stat_fixture_used_at: datetime | None = None
    mapping_status: str = "no_provider_id"
    warnings: list[str] = Field(default_factory=list)


class HistoricalLineupSideAudit(BaseModel):
    team_id: int
    team_name: str
    coverage: HistoricalLineupSideCoverage
    mapping: HistoricalLineupPlayerMappingSummary
    starters: list[HistoricalLineupPlayerPriorStats] = Field(default_factory=list)
    bench: list[HistoricalLineupPlayerPriorStats] = Field(default_factory=list)
    unavailable: list[HistoricalLineupPlayerPriorStats] = Field(default_factory=list)


class HistoricalLineupAuditFixtureResponse(BaseModel):
    status: str = "ok"
    preview_only: bool = True
    db_writes: bool = False
    audit_mode: str = "historical_official_xi"
    future_mode_hint: str = "historical_official_xi"
    competition_id: int
    competition_name: str
    fixture_id: int
    round: str | None = None
    kickoff_at: datetime
    cutoff_time: datetime
    fixture_status: str
    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int
    home: HistoricalLineupSideAudit
    away: HistoricalLineupSideAudit
    warnings: list[str] = Field(default_factory=list)
    feature_snapshot_json: dict[str, Any] = Field(default_factory=dict)


class HistoricalLineupAuditRoundFixtureBrief(BaseModel):
    fixture_id: int
    match: str
    round: str | None = None
    kickoff_at: datetime
    home_has_official_xi: bool = False
    away_has_official_xi: bool = False
    home_starters_count: int = 0
    away_starters_count: int = 0
    home_mapping_coverage_pct: float | None = None
    away_mapping_coverage_pct: float | None = None
    home_prior_stats_coverage_pct: float | None = None
    away_prior_stats_coverage_pct: float | None = None
    unavailable_data_present: bool = False
    source_timestamp_status: str = "missing"
    warnings: list[str] = Field(default_factory=list)


class HistoricalLineupAuditRoundSummary(BaseModel):
    fixtures_processed: int = 0
    fixtures_with_official_xi_both_teams: int = 0
    fixtures_with_partial_lineup: int = 0
    fixtures_without_lineup: int = 0
    avg_starters_count_home: float | None = None
    avg_starters_count_away: float | None = None
    avg_mapping_coverage_pct: float | None = None
    avg_player_stats_prior_coverage_pct: float | None = None
    fixtures_with_unavailable_data: int = 0
    fixtures_with_injured_data: int = 0
    fixtures_with_suspended_data: int = 0
    timestamp_safe_count: int = 0
    timestamp_missing_count: int = 0


class HistoricalLineupAuditRoundResponse(BaseModel):
    status: str = "ok"
    preview_only: bool = True
    db_writes: bool = False
    audit_mode: str = "historical_official_xi"
    future_mode_hint: str = "historical_official_xi"
    competition_id: int
    competition_name: str
    round_number: int
    limit: int
    offset: int
    summary: HistoricalLineupAuditRoundSummary
    fixtures: list[HistoricalLineupAuditRoundFixtureBrief] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
