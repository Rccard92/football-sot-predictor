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


class TeamPlayerLayerPointInTime(BaseModel):
    status: str
    formation: str | None = None
    starters_count: int = 0
    bench_count: int = 0
    mapping_coverage_pct: float | None = None
    prior_stats_coverage_pct: float | None = None
    offensive_xi_strength_index: float = 1.0
    top_shooter_presence_index: float = 1.0
    replacement_depth_index: float = 1.0
    player_layer_index: float = 1.0
    top_starters: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TeamLineupMacroPointInTime(BaseModel):
    status: str = "neutral_fallback"
    lineup_macro_index: float = 1.0
    formation: str | None = None
    starters_count: int = 0
    bench_count: int = 0
    previous_xi_overlap_count: int | None = None
    previous_xi_overlap_pct: float | None = None
    formation_changed_vs_previous: bool | None = None
    formation_changed_vs_common: bool | None = None
    components: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    fallback_variables: list[str] = Field(default_factory=list)


class TeamSplitPointInTimeStats(BaseModel):
    team_id: int
    split_context: str
    matches_count: int = 0
    avg_sot_for: float | None = None
    avg_sot_against: float | None = None
    avg_total_shots_for: float | None = None
    avg_total_shots_against: float | None = None
    avg_xg_for: float | None = None
    avg_xg_against: float | None = None
    latest_fixture_used_at: datetime | None = None
    status: str = "neutral_fallback"


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
    home_split_stats: TeamSplitPointInTimeStats
    away_split_stats: TeamSplitPointInTimeStats
    home_player_layer: TeamPlayerLayerPointInTime | None = None
    away_player_layer: TeamPlayerLayerPointInTime | None = None
    home_lineup_macro: TeamLineupMacroPointInTime | None = None
    away_lineup_macro: TeamLineupMacroPointInTime | None = None
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
