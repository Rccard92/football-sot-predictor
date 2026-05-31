"""Schemi API pick evaluation Over SOT read-only (Step H / H.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.services.backtest.sot_pick_evaluation_logic import (
    DEFAULT_CAUTIOUS_DROP_THRESHOLD,
    DEFAULT_PICK_LINES,
)
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig


class SotPickEvaluationRequest(BaseModel):
    competition_id: int
    mode: str = "historical_official_xi"
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    round_number: int | None = Field(default=None, ge=1)
    round_contains: str | None = None
    fixture_ids: list[int] | None = None
    lines: list[float] = Field(default_factory=lambda: list(DEFAULT_PICK_LINES))
    cautious_drop_threshold: float = Field(default=DEFAULT_CAUTIOUS_DROP_THRESHOLD, ge=0.0)
    include_no_pick: bool = True
    min_prior_matches_for_play: int = Field(default=10, ge=0)
    min_aggressive_edge_for_play: float = Field(default=0.25, ge=0.0)
    min_cautious_edge_for_play: float = Field(default=1.00, ge=0.0)
    max_warnings_for_play: int = Field(default=6, ge=0)
    allow_early_low_sample: bool = False
    allow_low_confidence: bool = False
    include_borderline_as_playable: bool = False

    def to_play_advice_config(self) -> PlayAdviceConfig:
        return PlayAdviceConfig(
            min_prior_matches_for_play=self.min_prior_matches_for_play,
            min_aggressive_edge_for_play=self.min_aggressive_edge_for_play,
            min_cautious_edge_for_play=self.min_cautious_edge_for_play,
            max_warnings_for_play=self.max_warnings_for_play,
            allow_early_low_sample=self.allow_early_low_sample,
            allow_low_confidence=self.allow_low_confidence,
            include_borderline_as_playable=self.include_borderline_as_playable,
        )


class SotPickEvaluationSelection(BaseModel):
    limit: int
    offset: int
    round_number: int | None = None
    round_contains: str | None = None
    round_filter_mode: str = "none"
    fixture_ids: list[int] | None = None
    lines: list[float]
    cautious_drop_threshold: float
    include_no_pick: bool = True
    order_by: str = "kickoff_at asc"
    min_prior_matches_for_play: int = 10
    min_aggressive_edge_for_play: float = 0.25
    min_cautious_edge_for_play: float = 1.00
    max_warnings_for_play: int = 6
    allow_early_low_sample: bool = False
    allow_low_confidence: bool = False
    include_borderline_as_playable: bool = False


class SotPickPlayAdvice(BaseModel):
    play_advice: str
    play_advice_label: str
    playability_score: int
    advice_reasons: list[str] = Field(default_factory=list)
    advice_summary: str = ""


class SotPickOverPick(BaseModel):
    side: str = "over"
    line: float
    edge: float
    outcome: str | None = None
    confidence: str
    play_advice: SotPickPlayAdvice | None = None


class SotPickEvaluationFixtureResult(BaseModel):
    fixture_id: int
    match: str
    round: str | None = None
    kickoff_at: datetime
    predicted_total_sot: float | None = None
    actual_total_sot: int | None = None
    total_abs_error: float | None = None
    aggressive_pick: SotPickOverPick | None = None
    cautious_pick: SotPickOverPick | None = None
    no_aggressive_pick: bool = True
    no_cautious_pick: bool = True
    warnings: list[str] = Field(default_factory=list)
    sample_bucket: str | None = None
    actual_total_bucket: str | None = None
    warnings_count: int = 0
    leakage_guard: bool = True
    home_prior_matches_count: int = 0
    away_prior_matches_count: int = 0
    home_lineup_macro_status: str | None = None
    home_lineup_macro_index: float | None = None
    away_lineup_macro_status: str | None = None
    away_lineup_macro_index: float | None = None
    home_unavailable_macro_index: float | None = None
    away_unavailable_macro_index: float | None = None
    unavailable_important_absences_count: int = 0
    source_fixture_id_lineup_home: int | None = None
    source_fixture_id_lineup_away: int | None = None
    source_fixture_id_unavailable_home: int | None = None
    source_fixture_id_unavailable_away: int | None = None


class SotPickCalculatedSummary(BaseModel):
    fixtures_processed: int = 0
    fixtures_failed: int = 0
    aggressive_calculated_count: int = 0
    aggressive_no_pick_count: int = 0
    aggressive_wins: int = 0
    aggressive_losses: int = 0
    aggressive_hit_rate: float | None = None
    cautious_calculated_count: int = 0
    cautious_no_pick_count: int = 0
    cautious_wins: int = 0
    cautious_losses: int = 0
    cautious_hit_rate: float | None = None
    avg_predicted_total_sot: float | None = None
    avg_actual_total_sot: float | None = None
    avg_total_abs_error: float | None = None
    break_even_odds_50_pct: float = 2.0


class SotPickAdvisedSummary(BaseModel):
    aggressive_play_count: int = 0
    aggressive_no_play_count: int = 0
    aggressive_borderline_count: int = 0
    aggressive_play_wins: int = 0
    aggressive_play_losses: int = 0
    aggressive_play_hit_rate: float | None = None
    cautious_play_count: int = 0
    cautious_no_play_count: int = 0
    cautious_borderline_count: int = 0
    cautious_play_wins: int = 0
    cautious_play_losses: int = 0
    cautious_play_hit_rate: float | None = None


class SotPickBreakdownLineStats(BaseModel):
    line: float
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
    calculated_summary: SotPickCalculatedSummary
    advised_summary: SotPickAdvisedSummary
    aggressive_by_line: list[SotPickBreakdownLineStats] = Field(default_factory=list)
    cautious_by_line: list[SotPickBreakdownLineStats] = Field(default_factory=list)
    aggressive_by_confidence: list[SotPickBreakdownConfidenceStats] = Field(default_factory=list)
    cautious_by_confidence: list[SotPickBreakdownConfidenceStats] = Field(default_factory=list)
    aggressive_by_sample_bucket: list[SotPickBreakdownSampleBucketStats] = Field(default_factory=list)
    cautious_by_sample_bucket: list[SotPickBreakdownSampleBucketStats] = Field(default_factory=list)
    aggressive_by_actual_total_bucket: list[SotPickBreakdownActualTotalBucketStats] = Field(
        default_factory=list,
    )
    cautious_by_actual_total_bucket: list[SotPickBreakdownActualTotalBucketStats] = Field(
        default_factory=list,
    )
    advised_aggressive_by_line: list[SotPickBreakdownLineStats] = Field(default_factory=list)
    advised_cautious_by_line: list[SotPickBreakdownLineStats] = Field(default_factory=list)
    advised_aggressive_by_confidence: list[SotPickBreakdownConfidenceStats] = Field(
        default_factory=list,
    )
    advised_cautious_by_confidence: list[SotPickBreakdownConfidenceStats] = Field(
        default_factory=list,
    )
    advised_aggressive_by_sample_bucket: list[SotPickBreakdownSampleBucketStats] = Field(
        default_factory=list,
    )
    advised_cautious_by_sample_bucket: list[SotPickBreakdownSampleBucketStats] = Field(
        default_factory=list,
    )
    results: list[SotPickEvaluationFixtureResult] = Field(default_factory=list)
    failed_fixtures: list[SotPickEvaluationFailedFixture] = Field(default_factory=list)
    feature_snapshot_json: dict[str, Any] = Field(default_factory=dict)
