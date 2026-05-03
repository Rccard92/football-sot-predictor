from typing import Any

from pydantic import BaseModel, Field


class RunBacktestBody(BaseModel):
    model_version: str = Field(..., description="Es. baseline_v0_1")
    default_lines: list[float] | None = Field(
        default=None,
        description="Linee da testare; default [2.5, 3.5, 4.5, 5.5, 6.5]",
    )


class RunBacktestResponse(BaseModel):
    batch_id: str
    season: int
    model_version: str
    rows_written: int


class BacktestSummaryResponse(BaseModel):
    batch_id: str
    season: int
    mae: float | None
    rmse: float | None
    hit_rate: float | None
    no_bet_rate: float | None
    total_predictions: int
    total_line_evaluations: int
    error_by_side: dict[str, dict[str, Any]]


class BacktestByTeamResponse(BaseModel):
    batch_id: str
    season: int
    error_by_team: dict[str, dict[str, Any]]


class BacktestByLineResponse(BaseModel):
    batch_id: str
    season: int
    error_by_line: dict[str, dict[str, Any]]
