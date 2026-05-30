"""Schemi API Backtest Engine — run management (Step C)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BacktestRunCreateRequest(BaseModel):
    competition_id: int
    season_year: int | None = None
    season_id: int | None = None
    market_key: str
    algorithm_version: str
    mode: str
    fixture_scope: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    config_json: dict[str, Any] | None = None
    model_manifest_version: str | None = None


class BacktestRunResponse(BaseModel):
    id: int
    competition_id: int
    season_id: int | None = None
    season_year: int | None = None
    market_key: str
    algorithm_version: str
    mode: str
    fixture_scope: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    status: str
    config_json: dict[str, Any]
    summary_json: dict[str, Any] | None = None
    error_json: dict[str, Any] | None = None
    algorithm_config_hash: str
    model_manifest_version: str | None = None
    git_commit_sha: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class BacktestRunListItem(BaseModel):
    id: int
    competition_id: int
    competition_name: str | None = None
    season_year: int | None = None
    market_key: str
    algorithm_version: str
    mode: str
    fixture_scope: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    summary_json: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class BacktestRunListResponse(BaseModel):
    items: list[BacktestRunListItem]
    total: int
    limit: int
    offset: int


class BacktestRunDetailResponse(BacktestRunResponse):
    competition_name: str | None = None
    predictions_count: int = 0
    picks_count: int = 0
    metrics_count: int = 0


class BacktestRunFilters(BaseModel):
    competition_id: int | None = None
    season_year: int | None = None
    market_key: str | None = None
    algorithm_version: str | None = None
    mode: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
