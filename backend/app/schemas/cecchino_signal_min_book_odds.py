"""Schemi API soglie minime quota book Cecchino."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SignalMinBookOddSettingItem(BaseModel):
    target_market_key: str
    label: str
    min_book_odd: float
    default_min_book_odd: float
    is_default: bool
    is_enabled: bool


class SignalMinBookOddSettingUpdateItem(BaseModel):
    target_market_key: str
    min_book_odd: float = Field(..., gt=1, le=50)


class SignalMinBookOddsSettingsResponse(BaseModel):
    status: str = "ok"
    items: list[SignalMinBookOddSettingItem]


class SignalMinBookOddsUpdateBody(BaseModel):
    items: list[SignalMinBookOddSettingUpdateItem]


class SignalMinBookOddsSaveAndBacktestBody(BaseModel):
    date_from: date
    date_to: date
    items: list[SignalMinBookOddSettingUpdateItem]
    rebuild_kpi_from_cache: bool = False
    include_xpt: bool = True
    force_remap_signals: bool = True
    evaluate_after: bool = True


class SignalMinBookOddsBacktestSummary(BaseModel):
    fixtures_seen: int = 0
    signals_rebuilt: int = 0
    si_cells_seen: int = 0
    value_passed: int = 0
    no_value_skipped: int = 0
    min_book_odd_skipped: int = 0
    deactivated_min_book_odd: int = 0
    missing_book_quote_skipped: int = 0
    missing_cecchino_quote_skipped: int = 0
    invalid_quote_skipped: int = 0
    deactivated_no_value: int = 0
    signals_created: int = 0
    signals_updated: int = 0
    signals_deactivated: int = 0
    evaluated: int = 0
    won: int = 0
    lost: int = 0
    pending: int = 0
    not_evaluable: int = 0
    models_processed: list[str] = Field(default_factory=list)
    models_value_passed: int = 0
    models_min_book_odd_skipped: int = 0
    models_deactivated_min_book_odd: int = 0


class SignalMinBookOddsSaveAndBacktestResponse(BaseModel):
    status: str
    settings: list[SignalMinBookOddSettingItem]
    backtest: SignalMinBookOddsBacktestSummary
    default_backtest: SignalMinBookOddsBacktestSummary | None = None
    models_backtest: dict | None = None
    errors: list[str] = []
