"""Schemas Bet Builder — contratto response BET-01 + BET-RESULTS-01 (documentazione OpenAPI)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BetBuilderOpportunitiesQuery(BaseModel):
    """Query documentata; l'endpoint usa Query FastAPI direttamente."""

    date: str = Field(..., description="Scan date YYYY-MM-DD")
    market_key: str | None = None
    origin: str | None = Field(
        default=None,
        description="price | signals | price_and_signals",
    )


class BetBuilderOpportunitiesResponse(BaseModel):
    """Contratto indicativo; payload reale è dict JSON (jsonable_encoder)."""

    contract_version: str
    aggregator_version: str
    signal_evidence_version: str | None = None
    purchasability_policy_version: str | None = None
    purchasability_policy: str
    scan_date: str
    source_revision: str
    source_generated_from: dict[str, Any] | None = None
    source_scan_status: str | None = None
    freshness: dict[str, Any]
    summary: dict[str, Any]
    opportunities: list[dict[str, Any]]


class BetBuilderResultsQuery(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    outcome: str | None = None
    match_status: str | None = None
    market_key: str | None = None
    origin: str | None = None
    min_purchasability: float | None = None
    sort: str | None = "recent"
    limit: int = 50
    offset: int = 0


class BetBuilderResultsResponse(BaseModel):
    """Contratto indicativo Results Monitor."""

    contract_version: str
    available_from: str
    primary_selection_version: str
    date_from: str
    date_to: str
    timezone: str
    sort: str
    limit: int
    offset: int
    total: int
    summary: dict[str, Any]
    fixtures: list[dict[str, Any]]


class BetBuilderResultAnalysisContextResponse(BaseModel):
    """Contratto indicativo analysis context (BET-RESULTS-02)."""

    contract_version: str
    fixture: dict[str, Any]
    kpi_panel: dict[str, Any] | None = None
    balance_v5: dict[str, Any] | None = None
    fixture_identity_consistency: dict[str, Any] | None = None
    balance_v5_snapshot_meta: dict[str, Any] | None = None
    goal_intensity_v5: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
