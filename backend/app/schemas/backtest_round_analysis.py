"""Schemi API analisi giornata persistente (Step I)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.sot_pick_evaluation_logic import DEFAULT_PICK_LINES

MODEL_API_ALIASES: dict[str, str] = {
    "baseline_v1_1": BASELINE_SOT_MODEL_VERSION_V11_SOT,
    "baseline_v1_1_sot": BASELINE_SOT_MODEL_VERSION_V11_SOT,
    "baseline_v2_0_lineup_impact": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    "baseline_v2_1_weighted_components": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
}

MODEL_LABELS: dict[str, str] = {
    BASELINE_SOT_MODEL_VERSION_V11_SOT: "v1.1",
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: "v2.0",
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: "v2.1",
}

DEFAULT_ROUND_ANALYSIS_MODELS: list[str] = [
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
]


def normalize_model_keys(models: list[str] | None) -> list[str]:
    if not models:
        return list(DEFAULT_ROUND_ANALYSIS_MODELS)
    out: list[str] = []
    for raw in models:
        key = MODEL_API_ALIASES.get(str(raw).strip())
        if key is None:
            raise ValueError(f"unsupported_model:{raw}")
        if key not in out:
            out.append(key)
    return out


class RoundAnalysisAdviceFilters(BaseModel):
    min_prior_matches_for_play: int = 10
    min_aggressive_edge_for_play: float = 0.25
    min_cautious_edge_for_play: float = 1.0
    max_warnings_for_play: int = 6
    allow_early_low_sample: bool = False
    allow_low_confidence: bool = False
    include_borderline_as_playable: bool = False


class RoundAnalysisAnalyzeRequest(BaseModel):
    competition_id: int
    season_year: int
    round_number: int = Field(..., ge=1, le=50)
    mode: str = BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
    models: list[str] | None = None
    lines: list[float] | None = None
    cautious_drop_threshold: float = 0.75
    advice_filters: RoundAnalysisAdviceFilters | None = None
    force_recalculate: bool = False

    @model_validator(mode="after")
    def _normalize(self) -> RoundAnalysisAnalyzeRequest:
        if self.lines is None:
            object.__setattr__(self, "lines", list(DEFAULT_PICK_LINES))
        if self.models is not None:
            object.__setattr__(self, "models", normalize_model_keys(self.models))
        return self


class RoundAnalysisModelSummary(BaseModel):
    model_key: str
    label: str
    fixtures: int = 0
    fixtures_ok: int = 0
    fixtures_nd: int = 0
    fixtures_error: int = 0
    aggressive_wins: int = 0
    aggressive_losses: int = 0
    aggressive_hit_rate: float | None = None
    cautious_wins: int = 0
    cautious_losses: int = 0
    cautious_hit_rate: float | None = None
    advised_plays: int = 0
    avg_predicted_total: float | None = None
    avg_actual_total: float | None = None
    mae: float | None = None
    bias: float | None = None
    predictions_available: int = 0
    no_prediction_count: int = 0
    display: str = "ND"
    prevalent_error_code: str | None = None
    model_engine_name: str | None = None


def season_label_from_year(year: int) -> str:
    return f"{int(year)}/{int(year) + 1}"


class RoundAnalysisDataQualitySummary(BaseModel):
    badge: Literal["OK", "Avvisi", "Critico"] = "OK"
    total_fixtures: int = 0
    fixtures_with_lineup: int = 0
    fixtures_with_unavailable: int = 0
    fixtures_missing_mapping: int = 0
    fixtures_player_layer_ok: int = 0
    fixtures_player_layer_partial: int = 0
    fixtures_player_layer_missing: int = 0
    player_layer_sides_available: int = 0
    player_layer_sides_total: int = 0
    fixtures_split_ok: int = 0
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class RoundAnalysisListItem(BaseModel):
    id: int
    competition_id: int
    season_year: int
    season_label: str
    round_number: int
    analysis_version: int
    status: str
    status_label: str | None = None
    status_reason: str | None = None
    mode: str
    total_fixtures: int
    processed_fixtures: int
    failed_fixtures: int
    progress_pct: float
    data_quality_badge: str | None = None
    data_quality_status: str | None = None
    accordion_summary: dict[str, str] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RoundAnalysisListResponse(BaseModel):
    items: list[RoundAnalysisListItem]
    total: int
    limit: int
    offset: int


class RoundAnalysisFixtureRow(BaseModel):
    id: int
    fixture_id: int
    round_number: int | None
    home_team_name: str
    away_team_name: str
    actual_home_sot: int | None
    actual_away_sot: int | None
    actual_total_sot: int | None
    models_json: dict[str, Any]
    explanation_json: dict[str, Any] | None = None
    status: str
    error_message: str | None = None


class RoundAnalysisDetailResponse(BaseModel):
    id: int
    competition_id: int
    season_year: int
    season_label: str
    round_number: int
    analysis_version: int
    status: str
    status_label: str | None = None
    status_reason: str | None = None
    data_quality_status: str | None = None
    mode: str
    config_json: dict[str, Any]
    total_fixtures: int
    processed_fixtures: int
    failed_fixtures: int
    failed_models_count: int = 0
    progress_pct: float
    data_quality_summary_json: dict[str, Any] | None = None
    model_summary_json: dict[str, Any] | None = None
    error_json: dict[str, Any] | None = None
    first_recommended_round: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
    fixtures: list[RoundAnalysisFixtureRow] = Field(default_factory=list)


class RoundAnalysisAnalyzeResponse(BaseModel):
    analysis: RoundAnalysisDetailResponse


class RoundAnalysisConflictResponse(BaseModel):
    code: str = "analysis_already_completed"
    message: str
    existing_analysis_id: int


class RoundAnalysisDeleteResponse(BaseModel):
    status: Literal["ok"] = "ok"
    deleted_analysis_id: int
    deleted_fixture_results: int
