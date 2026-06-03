"""Schemi API laboratorio predittivo persistente."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PredictiveRunCreateBody(BaseModel):
    competition_id: int
    season_year: int
    strategy: str = "all"
    strategy_status: str = "active"
    persist: bool = True
    use_latest_version_per_round: bool = True
    include_all_versions: bool = False


class PredictiveRunSummary(BaseModel):
    run_id: int | None = None
    summary: dict[str, Any]
    message: str
    audit: dict[str, Any] | None = None


class PredictiveRunListItem(BaseModel):
    run_id: int
    competition_id: int
    season_year: int
    season_label: str | None = None
    created_at: str | None = None
    fixtures_count: int
    strategies_count: int
    recommended_strategy: str | None = None
    best_mae_strategy: str | None = None
    main_warning: str | None = None
    run_type: str
    model_version: str


class PredictiveRunDetail(BaseModel):
    run_id: int
    competition_id: int
    season_year: int
    season_label: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    summary: dict[str, Any]
    simulator: dict[str, Any]
    pattern: dict[str, Any]
    insights: list[dict[str, Any]]
    audit: dict[str, Any]
    betting_phase_enabled: bool = False


class PredictiveFixtureNoteBody(BaseModel):
    strategy_key: str
    note: str
    tag: str | None = None


class PredictiveConfigResponse(BaseModel):
    openai_configured: bool


class PredictiveFixturesResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]


AnalysisType = Literal[
    "missed_high_non_extreme",
    "false_high_predictions",
    "top3_model_comparison",
    "single_fixture",
]


class PredictiveAiInsightsCreateBody(BaseModel):
    analysis_type: AnalysisType
    fixture_id: int | None = None
    strategy_key: str | None = None

    @model_validator(mode="after")
    def _validate_single_fixture(self) -> PredictiveAiInsightsCreateBody:
        if self.analysis_type == "single_fixture" and self.fixture_id is None:
            raise ValueError("fixture_id è obbligatorio per single_fixture")
        return self


class PredictiveAiInsightsHistoryResponse(BaseModel):
    items: list[dict[str, Any]]
