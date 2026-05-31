"""Schemi API pick evaluation Over/Under SOT read-only (Step H)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.services.backtest.sot_pick_evaluation_logic import DEFAULT_PICK_LINES


class SotPickEvaluationRequest(BaseModel):
    competition_id: int
    mode: str = "historical_official_xi"
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    round_number: int | None = Field(default=None, ge=1)
    round_contains: str | None = None
    fixture_ids: list[int] | None = None
    lines: list[float] = Field(default_factory=lambda: list(DEFAULT_PICK_LINES))
    min_edge: float = Field(default=0.75, ge=0.0)
    include_no_pick: bool = True


class SotPickEvaluationSelection(BaseModel):
    limit: int
    offset: int
    round_number: int | None = None
    round_contains: str | None = None
    round_filter_mode: str = "none"
    fixture_ids: list[int] | None = None
    lines: list[float]
    min_edge: float
    include_no_pick: bool = True
    order_by: str = "kickoff_at asc"


class SotPickLineEvaluation(BaseModel):
    line: float
    edge_over: float
    edge_under: float
    over_meets_min_edge: bool = False
    under_meets_min_edge: bool = False
    over_candidate: bool = False
    under_candidate: bool = False


class SotPickRecommendedPick(BaseModel):
    side: str
    line: float
    edge: float
    outcome: str | None = None
    confidence: str


class SotPickEvaluationFixtureResult(BaseModel):
    fixture_id: int
    match: str
    round: str | None = None
    kickoff_at: datetime
    predicted_total_sot: float | None = None
    actual_total_sot: int | None = None
    total_abs_error: float | None = None
    recommended_pick: SotPickRecommendedPick | None = None
    no_pick: bool = True
    all_line_evaluations: list[SotPickLineEvaluation] = Field(default_factory=list)
    sample_bucket: str | None = None
    actual_total_bucket: str | None = None
    warnings_count: int = 0
    leakage_guard: bool = True
    home_prior_matches_count: int = 0
    away_prior_matches_count: int = 0


class SotPickEvaluationSummary(BaseModel):
    fixtures_processed: int = 0
    fixtures_failed: int = 0
    pick_opportunities: int = 0
    no_pick_count: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    avg_edge: float | None = None
    avg_predicted_total_sot: float | None = None
    avg_actual_total_sot: float | None = None
    avg_total_abs_error: float | None = None
    over_picks_count: int = 0
    under_picks_count: int = 0
    over_wins: int = 0
    over_losses: int = 0
    under_wins: int = 0
    under_losses: int = 0
    break_even_odds_50_pct: float = 2.0


class SotPickBreakdownLineStats(BaseModel):
    line: float
    picks_count: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    avg_edge: float | None = None


class SotPickBreakdownSideStats(BaseModel):
    side: str
    picks_count: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    avg_edge: float | None = None


class SotPickBreakdownConfidenceStats(BaseModel):
    confidence: str
    picks_count: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    avg_edge: float | None = None


class SotPickBreakdownSampleBucketStats(BaseModel):
    bucket: str
    picks_count: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    avg_edge: float | None = None


class SotPickBreakdownActualTotalBucketStats(BaseModel):
    bucket: str
    picks_count: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    avg_edge: float | None = None


class SotPickEvaluationFailedFixture(BaseModel):
    fixture_id: int
    error_code: str
    message: str


class SotPickEvaluationResponse(BaseModel):
    status: str = "ok"
    preview_only: bool = True
    db_writes: bool = False
    market_key: str = "shots_on_target"
    algorithm_version: str = "baseline_v2_1_weighted_components"
    mode: str = "historical_official_xi"
    competition_id: int
    competition_name: str
    selection: SotPickEvaluationSelection
    summary: SotPickEvaluationSummary
    breakdown_by_line: list[SotPickBreakdownLineStats] = Field(default_factory=list)
    breakdown_by_side: list[SotPickBreakdownSideStats] = Field(default_factory=list)
    breakdown_by_confidence: list[SotPickBreakdownConfidenceStats] = Field(default_factory=list)
    breakdown_by_sample_bucket: list[SotPickBreakdownSampleBucketStats] = Field(default_factory=list)
    breakdown_by_actual_total_bucket: list[SotPickBreakdownActualTotalBucketStats] = Field(
        default_factory=list,
    )
    results: list[SotPickEvaluationFixtureResult] = Field(default_factory=list)
    failed_fixtures: list[SotPickEvaluationFailedFixture] = Field(default_factory=list)
    feature_snapshot_json: dict[str, Any] = Field(default_factory=dict)
