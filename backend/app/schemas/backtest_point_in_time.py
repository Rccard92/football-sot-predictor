"""Schemi API PointInTimeContext Backtest Engine (Step D)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BacktestFixtureTeamBrief(BaseModel):
    id: int
    name: str


class BacktestFixtureCandidate(BaseModel):
    fixture_id: int
    kickoff_at: datetime
    round: str | None = None
    status: str
    home_team: BacktestFixtureTeamBrief
    away_team: BacktestFixtureTeamBrief
    has_team_stats: bool = False
    actual_total_sot: int | None = None


class BacktestFixtureListResponse(BaseModel):
    items: list[BacktestFixtureCandidate]
    total: int
    limit: int
    offset: int


class TeamLast5Form(BaseModel):
    last5_avg_sot_for: float | None = None
    last5_avg_sot_against: float | None = None
    last5_avg_xg_for: float | None = None
    last5_avg_xg_against: float | None = None
    last5_count: int = 0
    status: str = "ok"


class TeamPointInTimeStats(BaseModel):
    team_id: int
    team_name: str
    avg_sot_for: float | None = None
    avg_sot_against: float | None = None
    avg_total_shots_for: float | None = None
    avg_total_shots_against: float | None = None
    avg_xg_for: float | None = None
    avg_xg_against: float | None = None
    sample_count: int = 0
    latest_fixture_used_at: datetime | None = None
    last5: TeamLast5Form = Field(default_factory=TeamLast5Form)


class LeaguePointInTimeBaselines(BaseModel):
    league_avg_sot_for: float | None = None
    league_avg_sot_against: float | None = None
    league_avg_total_shots: float | None = None
    league_avg_xg_for: float | None = None
    league_avg_xg_conceded: float | None = None
    sample_count: int = 0
    latest_fixture_used_at: datetime | None = None


class PlayerStatsDiagnostic(BaseModel):
    player_match_stats_prior_count: int = 0
    unique_players_prior_count: int = 0
    latest_player_stat_fixture_used_at: datetime | None = None


class LineupDiagnostic(BaseModel):
    lineup_mode: str
    lineups_available: bool = False
    lineups_count: int = 0


class ActualsForScoring(BaseModel):
    actual_home_sot: int | None = None
    actual_away_sot: int | None = None
    actual_total_sot: int | None = None
    final_score: str | None = None
    fixture_status: str | None = None


class PointInTimeContextResponse(BaseModel):
    competition_id: int
    competition_key: str
    competition_name: str
    fixture_id: int
    fixture_kickoff_at: datetime
    fixture_round: str | None = None
    fixture_status: str
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    mode: str
    market_key: str = "shots_on_target"
    cutoff_time: datetime
    leakage_guard: bool = True
    latest_fixture_used_at: datetime | None = None
    prior_fixtures_count: int = 0
    home_prior_matches_count: int = 0
    away_prior_matches_count: int = 0
    league_prior_matches_count: int = 0
    home_team_stats: TeamPointInTimeStats
    away_team_stats: TeamPointInTimeStats
    league_baselines: LeaguePointInTimeBaselines
    home_player_stats: PlayerStatsDiagnostic
    away_player_stats: PlayerStatsDiagnostic
    lineup_diagnostic: LineupDiagnostic
    actuals_for_scoring: ActualsForScoring
    actuals_used_as_input: bool = False
    source_paths: list[str] = Field(default_factory=list)
    missing_variables: list[str] = Field(default_factory=list)
    fallback_variables: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    feature_snapshot_json: dict[str, Any] = Field(default_factory=dict)
