"""Schema API usage summary."""

from __future__ import annotations

from pydantic import BaseModel


class ApiUsageByJobItem(BaseModel):
    job_id: str
    calls: int


class ApiUsageSummaryResponse(BaseModel):
    date: str
    total_calls: int
    by_endpoint: dict[str, int]
    by_job: list[ApiUsageByJobItem]
    cache_hits: int
    negative_cache_hits: int
    estimated_remaining_daily_budget: int
