"""Schemi API mini-run preview SOT v2.1 point-in-time (Step F)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.backtest_sot_v21_preview import SotV21PreviewSideTrace


class SotV21MiniRunRequest(BaseModel):
    competition_id: int
    mode: str = "pre_lineup"
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    round_number: int | None = Field(default=None, ge=1)
    round_contains: str | None = None
    fixture_ids: list[int] | None = None
    include_trace: bool = False


class SotV21MiniRunSelection(BaseModel):
    limit: int
    offset: int
    round_number: int | None = None
    round_contains: str | None = None
    round_filter_mode: str = "none"
    fixture_ids: list[int] | None = None
    order_by: str = "kickoff_at asc"


class SotV21MiniRunSummary(BaseModel):
    fixtures_requested: int = 0
    fixtures_processed: int = 0
    fixtures_failed: int = 0
    total_mae: float | None = None
    home_mae: float | None = None
    away_mae: float | None = None
    total_rmse: float | None = None
    total_bias: float | None = None
    home_bias: float | None = None
    away_bias: float | None = None
    avg_predicted_total_sot: float | None = None
    avg_actual_total_sot: float | None = None
    overestimated_count: int = 0
    underestimated_count: int = 0
    exact_or_near_count: int = 0
    high_error_count: int = 0


class SotV21MiniRunBucketStats(BaseModel):
    fixtures_count: int = 0
    total_mae: float | None = None
    total_bias: float | None = None
    avg_predicted_total_sot: float | None = None
    avg_actual_total_sot: float | None = None


class SotV21MiniRunSampleBreakdown(BaseModel):
    early_low_sample: SotV21MiniRunBucketStats = Field(default_factory=SotV21MiniRunBucketStats)
    medium_sample: SotV21MiniRunBucketStats = Field(default_factory=SotV21MiniRunBucketStats)
    stable_sample: SotV21MiniRunBucketStats = Field(default_factory=SotV21MiniRunBucketStats)


class SotV21MiniRunActualTotalBreakdown(BaseModel):
    low_total: SotV21MiniRunBucketStats = Field(default_factory=SotV21MiniRunBucketStats)
    medium_total: SotV21MiniRunBucketStats = Field(default_factory=SotV21MiniRunBucketStats)
    high_total: SotV21MiniRunBucketStats = Field(default_factory=SotV21MiniRunBucketStats)


class SotV21MiniRunFixtureResult(BaseModel):
    fixture_id: int
    round: str | None = None
    kickoff_at: datetime
    home_team: str
    away_team: str
    predicted_home_sot: float | None = None
    predicted_away_sot: float | None = None
    predicted_total_sot: float | None = None
    actual_home_sot: int | None = None
    actual_away_sot: int | None = None
    actual_total_sot: int | None = None
    home_error: float | None = None
    away_error: float | None = None
    total_error: float | None = None
    total_abs_error: float | None = None
    leakage_guard: bool = True
    actuals_used_as_input: bool = False
    latest_fixture_used_at: datetime | None = None
    cutoff_time: datetime
    home_prior_matches_count: int = 0
    away_prior_matches_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    home_trace: SotV21PreviewSideTrace | None = None
    away_trace: SotV21PreviewSideTrace | None = None


class SotV21MiniRunCaseBrief(BaseModel):
    fixture_id: int
    kickoff_at: datetime
    round: str | None = None
    home_team: str
    away_team: str
    predicted_home_sot: float | None = None
    predicted_away_sot: float | None = None
    predicted_total_sot: float | None = None
    actual_home_sot: int | None = None
    actual_away_sot: int | None = None
    actual_total_sot: int | None = None
    total_error: float | None = None
    total_abs_error: float | None = None
    home_prior_matches_count: int = 0
    away_prior_matches_count: int = 0
    warnings_count: int = 0


class SotV21MiniRunFailedFixture(BaseModel):
    fixture_id: int
    error_code: str
    message: str


class SotV21MiniRunResponse(BaseModel):
    status: str = "ok"
    preview_only: bool = True
    market_key: str = "shots_on_target"
    algorithm_version: str = "baseline_v2_1_weighted_components"
    competition_id: int
    competition_name: str
    mode: str = "pre_lineup"
    selection: SotV21MiniRunSelection
    summary: SotV21MiniRunSummary
    sample_breakdown: SotV21MiniRunSampleBreakdown = Field(default_factory=SotV21MiniRunSampleBreakdown)
    actual_total_breakdown: SotV21MiniRunActualTotalBreakdown = Field(
        default_factory=SotV21MiniRunActualTotalBreakdown,
    )
    worst_cases: list[SotV21MiniRunCaseBrief] = Field(default_factory=list)
    best_cases: list[SotV21MiniRunCaseBrief] = Field(default_factory=list)
    results: list[SotV21MiniRunFixtureResult] = Field(default_factory=list)
    failed_fixtures: list[SotV21MiniRunFailedFixture] = Field(default_factory=list)
    db_writes: bool = False
    feature_snapshot_json: dict[str, Any] = Field(default_factory=dict)
