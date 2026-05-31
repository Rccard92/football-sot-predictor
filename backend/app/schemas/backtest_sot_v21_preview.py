"""Schemi API preview SOT v2.1 point-in-time (Step E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.backtest_point_in_time import ActualsForScoring


class SotV21PreviewFixtureBrief(BaseModel):
    home_team: str
    away_team: str
    kickoff_at: datetime
    round: str | None = None


class SotV21PreviewPrediction(BaseModel):
    home_predicted_sot: float | None = None
    away_predicted_sot: float | None = None
    total_predicted_sot: float | None = None


class SotV21PreviewErrors(BaseModel):
    home_error: float | None = None
    away_error: float | None = None
    total_error: float | None = None
    home_abs_error: float | None = None
    away_abs_error: float | None = None
    total_abs_error: float | None = None


class SotV21PreviewMacroTrace(BaseModel):
    key: str
    label: str
    macro_weight: int
    macro_index: float
    status: str
    warnings: list[str] = Field(default_factory=list)
    components: dict[str, Any] | None = None
    source_paths: list[str] | None = None
    details: dict[str, Any] | None = None
    mode: str | None = None
    source_fixture_id: int | None = None


class SotV21PreviewSideTrace(BaseModel):
    base_anchor_sot: dict[str, Any]
    weighted_macro_multiplier: float
    expected_sot_v21_pit: float | None = None
    macros: list[SotV21PreviewMacroTrace] = Field(default_factory=list)


class SotV21PreviewResponse(BaseModel):
    status: str = "ok"
    market_key: str = "shots_on_target"
    algorithm_version: str = "baseline_v2_1_weighted_components"
    mode: str = "pre_lineup"
    competition_id: int
    fixture_id: int
    fixture: SotV21PreviewFixtureBrief
    leakage_guard: bool = True
    cutoff_time: datetime
    latest_fixture_used_at: datetime | None = None
    actuals_used_as_input: bool = False
    prediction: SotV21PreviewPrediction
    actuals_for_scoring: ActualsForScoring
    errors: SotV21PreviewErrors
    home_trace: SotV21PreviewSideTrace
    away_trace: SotV21PreviewSideTrace
    home_prior_matches_count: int = 0
    away_prior_matches_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    fallback_variables: list[str] = Field(default_factory=list)
    feature_snapshot_json: dict[str, Any] = Field(default_factory=dict)
