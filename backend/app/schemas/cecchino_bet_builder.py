"""Schemas Bet Builder — contratto response BET-01 (documentazione OpenAPI)."""

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
