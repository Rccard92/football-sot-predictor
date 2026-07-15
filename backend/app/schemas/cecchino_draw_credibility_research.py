"""Schemi API audit storico Credibilità X — Fase 1A/1B."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class _DateRangeMixin(BaseModel):
    date_from: date
    date_to: date
    competition_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from deve essere <= date_to")
        if (self.date_to - self.date_from).days > 365 * 5:
            raise ValueError("Il range massimo consentito è 5 anni")
        return self


class CecchinoDrawCredibilityAuditBody(_DateRangeMixin):
    only_eligible: bool = True


class CecchinoDrawCredibilityDatasetBody(_DateRangeMixin):
    cohort: Literal["eligible_primary", "all_usable_sensitivity", "market_subset"] = "eligible_primary"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=10, le=500)


class CecchinoDrawCredibilityDatasetExportBody(_DateRangeMixin):
    cohort: Literal["eligible_primary", "all_usable_sensitivity", "market_subset"] = "eligible_primary"


class DrawCredibilityExclusionReasonRow(BaseModel):
    reason: str
    count: int
    pct_total: float
    pct_finished: float


class DrawCredibilityLeagueRow(BaseModel):
    country_name: str
    league_name: str
    competition_id: int | None
    total: int
    finished: int
    draws: int
    internal_usable: int
    market_usable: int
    internal_coverage_pct: float
    market_coverage_pct: float


class DrawCredibilityMonthRow(BaseModel):
    month: str
    total: int
    finished: int
    draws: int
    internal_usable: int
    market_usable: int


class DrawCredibilityDebugSample(BaseModel):
    today_fixture_id: int
    provider_fixture_id: int
    scan_date: str | None
    home_team: str | None
    away_team: str | None
    league_name: str | None
    reason: str
