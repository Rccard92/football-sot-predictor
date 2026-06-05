"""Contesto opzionale per tracking chiamate API-Football."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ApiUsageContext:
    job_id: str | None = None
    scan_date: date | None = None
    provider_fixture_id: int | None = None
    provider_league_id: int | None = None
    cache_hit: bool = False
    negative_cache_hit: bool = False
    record_events: bool = True

    def with_fixture(self, provider_fixture_id: int | None) -> ApiUsageContext:
        return ApiUsageContext(
            job_id=self.job_id,
            scan_date=self.scan_date,
            provider_fixture_id=provider_fixture_id,
            provider_league_id=self.provider_league_id,
            cache_hit=self.cache_hit,
            negative_cache_hit=self.negative_cache_hit,
            record_events=self.record_events,
        )

    def with_league(self, provider_league_id: int | None) -> ApiUsageContext:
        return ApiUsageContext(
            job_id=self.job_id,
            scan_date=self.scan_date,
            provider_fixture_id=self.provider_fixture_id,
            provider_league_id=provider_league_id,
            cache_hit=self.cache_hit,
            negative_cache_hit=self.negative_cache_hit,
            record_events=self.record_events,
        )


@dataclass
class BudgetGuardStop(Exception):
    """Scan interrotta per protezione budget API."""

    status: str
    message: str
    api_calls_total: int = 0
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message
