"""Metriche run scan Cecchino Today (API calls, odds strategy, timing)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanRunMetrics:
    started_at: float = 0.0
    fixtures_found: int = 0
    after_competition_filter: int = 0
    odds_checked: int = 0
    odds_from_cache: int = 0
    odds_from_api: int = 0
    api_calls: dict[str, int] = field(
        default_factory=lambda: {"odds": 0, "fixtures": 0, "teams": 0},
    )
    odds_strategy: dict[str, int] = field(
        default_factory=lambda: {
            "fixture_single_call": 0,
            "fixture_single_call_with_bookmaker_fallback": 0,
            "bookmaker_per_fixture": 0,
            "cached": 0,
        },
    )
    excluded_summary: dict[str, int] = field(default_factory=dict)

    def record_odds_strategy(self, strategy: str) -> None:
        if strategy == "cached":
            self.odds_from_cache += 1
            self.odds_strategy["cached"] = self.odds_strategy.get("cached", 0) + 1
        elif strategy in self.odds_strategy:
            self.odds_strategy[strategy] += 1
            self.odds_from_api += 1
        else:
            self.odds_from_api += 1

    def to_result_summary(
        self,
        *,
        fixtures_found: int,
        after_competition_filter: int,
        odds_checked: int,
        eligible_count: int,
        excluded_count: int,
        excluded_summary: dict[str, int],
        duration_seconds: float,
    ) -> dict[str, Any]:
        return {
            "fixtures_found": fixtures_found,
            "after_competition_filter": after_competition_filter,
            "odds_checked": odds_checked,
            "odds_from_cache": self.odds_from_cache,
            "odds_from_api": self.odds_from_api,
            "eligible_count": eligible_count,
            "excluded_count": excluded_count,
            "excluded_summary": dict(excluded_summary),
            "api_calls": dict(self.api_calls),
            "odds_strategy": dict(self.odds_strategy),
            "duration_seconds": round(duration_seconds, 2),
        }
