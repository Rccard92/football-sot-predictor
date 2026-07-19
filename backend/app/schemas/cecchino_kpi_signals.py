"""Schemi API Segnali KPI Cecchino."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CecchinoKpiSignalsBackfillBody(BaseModel):
    date_from: date
    date_to: date
    only_missing: bool = True
    evaluate_after: bool = True


class CecchinoKpiSignalsRevaluateBody(BaseModel):
    date_from: date
    date_to: date


class CecchinoPurchasabilityValidationSyncBody(BaseModel):
    date_from: date
    date_to: date
    evaluate_after: bool = True
    include_legacy_derived: bool = False


class CecchinoPurchasabilityValidationJobBody(BaseModel):
    date_from: date
    date_to: date
    candidate_version: str | None = None
    competition_id: int | None = None
    market_key: str | None = None
    bootstrap_iterations: int = Field(default=200, ge=10, le=2000)
    promotion_eligible_only: bool = True
