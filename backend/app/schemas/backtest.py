from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.constants import BASELINE_SOT_MODEL_VERSION


class RunNumericBacktestBody(BaseModel):
    model_version: str = Field(default=BASELINE_SOT_MODEL_VERSION)


class RunBacktestBody(BaseModel):
    """Legacy: linee over/under (flusso precedente)."""

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


class NumericBacktestErrorItem(BaseModel):
    prediction_id: int
    fixture_id: int
    team_id: int
    message: str


class RunNumericBacktestResponse(BaseModel):
    status: Literal["pending", "success", "error"]
    season: int
    model_version: str
    predictions_total: int = 0
    backtests_created_or_updated: int = 0
    mae: float = 0.0
    rmse: float = 0.0
    avg_expected_sot: float = 0.0
    avg_actual_sot: float = 0.0
    errors: list[NumericBacktestErrorItem] = Field(default_factory=list)
    ingestion_run_id: int | None = None
    message: str | None = None


class BacktestNumericSummaryResponse(BaseModel):
    season: int
    model_version: str
    predictions_total: int
    backtests_total: int
    coverage_pct: float
    mae: float
    rmse: float
    avg_expected_sot: float
    avg_actual_sot: float
    avg_absolute_error: float
    max_absolute_error: float


class BacktestByTeamRow(BaseModel):
    team_id: int
    team_name: str
    predictions_count: int
    avg_expected_sot: float
    avg_actual_sot: float
    mae: float
    rmse: float
    max_absolute_error: float


class BacktestByTeamListResponse(BaseModel):
    season: int
    model_version: str
    teams: list[BacktestByTeamRow]


class BacktestBySideRow(BaseModel):
    side: str
    predictions_count: int
    avg_expected_sot: float
    avg_actual_sot: float
    mae: float
    rmse: float


class BacktestBySideListResponse(BaseModel):
    season: int
    model_version: str
    sides: list[BacktestBySideRow]


class BacktestFixtureCompareItem(BaseModel):
    team_name: str
    side: str
    expected_sot: float
    actual_sot: float
    absolute_error: float | None
    confidence_score: int | None


class BacktestFixtureCompareResponse(BaseModel):
    fixture_id: int
    model_version: str
    rows: list[BacktestFixtureCompareItem]


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
