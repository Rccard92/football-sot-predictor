"""Schemi API overview aggregato Round Analysis."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.backtest_round_analysis import MODEL_LABELS


class ModeAdviceCounts(BaseModel):
    GIOCA: int = 0
    NON_GIOCARE: int = Field(0, alias="NON GIOCARE")
    BORDERLINE: int = 0

    model_config = {"populate_by_name": True}


class ModePlayStats(BaseModel):
    plays: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    display: str = ""


class ModePlayStatsExtended(ModePlayStats):
    advised: ModePlayStats = Field(default_factory=ModePlayStats)
    calculated: ModePlayStats = Field(default_factory=ModePlayStats)
    advice_counts: dict[str, int] = Field(default_factory=dict)


class ModelTrendLast5(BaseModel):
    hit_rate: float | None = None
    direction: Literal["up", "down", "flat"] = "flat"
    rounds: list[int] = Field(default_factory=list)


class LinePickStats(BaseModel):
    wins: int = 0
    losses: int = 0
    hit_rate: float | None = None
    display: str = ""


class ModelOverviewStats(BaseModel):
    model_key: str
    label: str
    fixtures_analyzed: int = 0
    rounds_count: int = 0
    aggressive: ModePlayStatsExtended = Field(default_factory=ModePlayStatsExtended)
    cautious: ModePlayStatsExtended = Field(default_factory=ModePlayStatsExtended)
    reliability_score: float | None = None
    reliability_mode: Literal["pick_selected", "weighted_ca"] | None = None
    sample_status: Literal["provvisorio", "medio", "solido"] = "provvisorio"
    trend_last_5_rounds: ModelTrendLast5 = Field(default_factory=ModelTrendLast5)
    mae: float | None = None
    bias: float | None = None
    advised_plays_total: int = 0
    no_bet_count: int = 0
    borderline_count: int = 0
    line_6_5: LinePickStats | None = None
    line_7_5: LinePickStats | None = None
    aggressive_na: bool = False


class RoundOverviewModelChip(BaseModel):
    cautious_display: str = ""
    aggressive_display: str = ""
    cautious_hit_rate: float | None = None
    aggressive_hit_rate: float | None = None


class RoundOverviewItem(BaseModel):
    analysis_id: int
    round_number: int
    analysis_version: int
    status: str
    total_fixtures: int = 0
    processed_fixtures: int = 0
    data_quality_badge: str | None = None
    models: dict[str, RoundOverviewModelChip] = Field(default_factory=dict)
    summary_source: Literal["persisted", "rebuilt_from_fixtures"] | None = None
    completeness: Literal["ok", "stale", "empty"] | None = None
    stale_message: str | None = None


class RoundAnalysisOverviewResponse(BaseModel):
    competition_id: int
    season_year: int
    season_label: str
    use_latest_version_per_round: bool = True
    rounds_analyzed: int = 0
    fixtures_analyzed: int = 0
    models: dict[str, ModelOverviewStats] = Field(default_factory=dict)
    rounds: list[RoundOverviewItem] = Field(default_factory=list)
    ranking: dict[str, Any] = Field(default_factory=dict)


def model_label(model_key: str) -> str:
    return MODEL_LABELS.get(model_key, model_key)
