"""Schemi snapshot formazione/indisponibili fixture target (Step J/K)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.backtest_historical_lineup_audit import HistoricalLineupSideCoverage


class HistoricalSnapshotPlayerRow(BaseModel):
    player_name: str
    provider_player_id: int | None = None
    api_player_id: int | None = None
    position: str | None = None
    is_starter: bool = False
    is_unavailable: bool = False
    absence_group: str | None = None


class HistoricalFixtureSideSnapshot(BaseModel):
    team_id: int
    side: str
    status: str = "available"
    formation: str | None = None
    coverage: HistoricalLineupSideCoverage = Field(default_factory=HistoricalLineupSideCoverage)
    starters: list[HistoricalSnapshotPlayerRow] = Field(default_factory=list)
    bench: list[HistoricalSnapshotPlayerRow] = Field(default_factory=list)
    unavailable: list[HistoricalSnapshotPlayerRow] = Field(default_factory=list)
    injured: list[HistoricalSnapshotPlayerRow] = Field(default_factory=list)
    suspended: list[HistoricalSnapshotPlayerRow] = Field(default_factory=list)
    source_table: str | None = None
    source_provider: str | None = None
    source_timestamp_status: str = "missing"
    unavailable_source: str = "none"
    warnings: list[str] = Field(default_factory=list)


class HistoricalFixtureOfficialSnapshot(BaseModel):
    fixture_id: int
    competition_id: int
    home_team_id: int
    away_team_id: int
    cutoff_time: datetime
    home: HistoricalFixtureSideSnapshot
    away: HistoricalFixtureSideSnapshot
    warnings: list[str] = Field(default_factory=list)
