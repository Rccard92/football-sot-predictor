"""Schema query research Indice di Acquistabilità (Fase 1)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CecchinoPurchasabilityAuditQuery(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    competition_id: int | None = None
    market_family: str | None = None
    book_source: str | None = None


class CecchinoPurchasabilityDatasetQuery(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    competition_id: int | None = None
    market_family: str | None = None
    book_source: str | None = None
    status: str | None = Field(
        default=None,
        description="all|core|settled|pre_match|excluded",
    )
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CecchinoPurchasabilityStatisticalResearchQuery(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    competition_id: int | None = None
    market_family: str | None = None
    selection: str | None = None
    bootstrap_iterations: int = Field(default=200, ge=10, le=2000)
    seed: int = Field(default=42)


class CecchinoPurchasabilityStatisticalJobBody(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    competition_id: int | None = None
    market_family: str | None = None
    selection: str | None = None
    bootstrap_iterations: int = Field(default=200, ge=10, le=2000)
    seed: int = Field(default=42)
