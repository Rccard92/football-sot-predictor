"""Metriche run scan Cecchino Today (API calls, odds strategy, timing, funnel).

Book coverage counters (diagnostici, non alterano policy/selezione):

- betfair_primary_used / bet365_fallback_used:
  numero di *fixture* con almeno una selection canonica dalla fonte.
- betfair_primary_selection_count / bet365_fallback_selection_count:
  numero di *selection canoniche* risolte da Betfair primario / Bet365 fallback.
- book_still_missing_after_fallback:
  selection canoniche ancora N/D dopo il ciclo completo Betfair → Bet365.
- bet365_fallback_fixture_count:
  fixture con almeno una selection via Bet365 fallback.
- book_coverage_fixture_count:
  fixture stats-qualified che hanno contribuito UNA volta al monitor full Book
  (Phase B post-stats; non include gate intermedi).
- Integrity (MONITOR-01.1): expected = fixture_count * len(CANONICAL_BOOK_SELECTION_KEYS);
  actual = bf + b365 + missing; consistent = expected == actual.
  Warning diagnostico non-blocking se mismatch con fixture_count > 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.cecchino.cecchino_canonical_book_resolver import (
    CANONICAL_BOOK_SELECTION_KEYS,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOK_POLICY_VERSION
from app.services.cecchino.cecchino_today_eligible_guard import empty_eligibility_transitions


def book_coverage_integrity_warning(fields: dict[str, Any]) -> str | None:
    """Warning diagnostico se i contatori coverage non quadrano (non-blocking).

    Nessun warning se fixture_count == 0 (evita falsi errori su metrics vuote).
    Non altera counters né eligibility.
    """
    fixture_count = int(fields.get("book_coverage_fixture_count") or 0)
    if fixture_count <= 0:
        return None
    if fields.get("book_coverage_consistent") is True:
        return None
    keys = int(fields.get("book_selection_keys_count") or 0)
    expected = int(fields.get("book_coverage_expected_selection_count") or 0)
    actual = int(fields.get("book_coverage_actual_selection_count") or 0)
    bf = int(fields.get("betfair_primary_selection_count") or 0)
    b365 = int(fields.get("bet365_fallback_selection_count") or 0)
    missing = int(fields.get("book_still_missing_after_fallback") or 0)
    return (
        "book_coverage_counter_mismatch "
        f"fixtures={fixture_count} "
        f"selection_keys_count={keys} "
        f"expected={expected} "
        f"actual={actual} "
        f"BF={bf} "
        f"B365={b365} "
        f"missing={missing}"
    )


@dataclass
class ScanRunMetrics:
    started_at: float = 0.0
    fixtures_found: int = 0
    fixtures_censused: int = 0
    after_competition_filter: int = 0
    fixtures_after_competition_gate: int = 0
    fixtures_after_bookmaker_gate: int = 0
    fixtures_after_stats_gate: int = 0
    odds_checked: int = 0
    odds_from_cache: int = 0
    odds_from_api: int = 0
    odds_cache_hits: int = 0
    negative_cache_hits: int = 0
    stats_checked: int = 0
    bookmaker_fallback_count: int = 0
    betfair_primary_used: int = 0  # fixture-count (≥1 selection Betfair)
    betfair_primary_selection_count: int = 0  # selection-count Betfair
    bet365_fallback_used: int = 0  # fixture-count (≥1 selection Bet365)
    bet365_fallback_selection_count: int = 0  # selection-count Bet365
    bet365_fallback_fixture_count: int = 0  # alias semantico di bet365_fallback_used
    book_still_missing_after_fallback: int = 0  # selection-count ancora N/D
    book_coverage_fixture_count: int = 0  # fixture stats-qualified con full Book coverage
    api_calls_total: int = 0
    api_calls: dict[str, int] = field(
        default_factory=lambda: {"odds": 0, "fixtures": 0, "teams": 0},
    )
    odds_strategy: dict[str, int] = field(
        default_factory=lambda: {
            "fixture_single_call": 0,
            "fixture_single_call_with_bookmaker_fallback": 0,
            "fixture_single_call_with_bet365_fallback": 0,
            "bookmaker_per_fixture": 0,
            "betfair_1x2": 0,
            "betfair_1x2_with_bet365_fallback": 0,
            "odds_incomplete_1x2_gate": 0,
            "cached": 0,
            "negative_cache": 0,
        },
    )
    excluded_summary: dict[str, int] = field(default_factory=dict)
    eligibility_transitions: dict[str, int] = field(default_factory=empty_eligibility_transitions)
    protected_eligible_total: int = 0
    protected_snapshot_overwrite_blocked: int = 0
    budget_remaining_estimated: int | None = None

    def record_transition(self, transition: str) -> None:
        self.eligibility_transitions[transition] = int(
            self.eligibility_transitions.get(transition, 0)
        ) + 1

    def record_odds_strategy(self, strategy: str) -> None:
        if strategy == "cached":
            self.odds_from_cache += 1
            self.odds_cache_hits += 1
            self.odds_strategy["cached"] = self.odds_strategy.get("cached", 0) + 1
        elif strategy == "negative_cache":
            self.negative_cache_hits += 1
            self.odds_strategy["negative_cache"] = self.odds_strategy.get("negative_cache", 0) + 1
        elif strategy == "odds_incomplete_1x2_gate":
            self.odds_strategy["odds_incomplete_1x2_gate"] = (
                self.odds_strategy.get("odds_incomplete_1x2_gate", 0) + 1
            )
            self.odds_from_api += 1
        elif strategy in self.odds_strategy:
            self.odds_strategy[strategy] += 1
            self.odds_from_api += 1
            if "fallback" in strategy or strategy == "bookmaker_per_fixture":
                self.bookmaker_fallback_count += 1
        else:
            self.odds_strategy[strategy] = self.odds_strategy.get(strategy, 0) + 1
            self.odds_from_api += 1
            if "fallback" in strategy:
                self.bookmaker_fallback_count += 1

    def sync_api_calls_total(self) -> None:
        self.api_calls_total = sum(int(v) for v in self.api_calls.values())

    def book_coverage_fields(self) -> dict[str, Any]:
        """Patch diagnostico Book coverage per result_summary (live + finale)."""
        bf = int(self.betfair_primary_selection_count or 0)
        b365 = int(self.bet365_fallback_selection_count or 0)
        missing = int(self.book_still_missing_after_fallback or 0)
        resolved = bf + b365
        total = resolved + missing
        coverage_pct: float | None
        if total > 0:
            coverage_pct = round(resolved / total * 100, 1)
        else:
            coverage_pct = None
        fixture_count = int(self.book_coverage_fixture_count or 0)
        selection_keys_count = len(CANONICAL_BOOK_SELECTION_KEYS)
        expected_selection_count = fixture_count * selection_keys_count
        actual_selection_count = bf + b365 + missing
        consistent = expected_selection_count == actual_selection_count
        return {
            "betfair_primary_used": int(self.betfair_primary_used or 0),
            "betfair_primary_selection_count": bf,
            "bet365_fallback_used": int(self.bet365_fallback_used or 0),
            "bet365_fallback_selection_count": b365,
            "bet365_fallback_fixture_count": int(self.bet365_fallback_fixture_count or 0),
            "book_still_missing_after_fallback": missing,
            "book_coverage_fixture_count": fixture_count,
            "book_coverage_pct": coverage_pct,
            "book_selection_keys_count": selection_keys_count,
            "book_coverage_expected_selection_count": expected_selection_count,
            "book_coverage_actual_selection_count": actual_selection_count,
            "book_coverage_consistent": consistent,
            "bookmaker_mode": CECCHINO_BOOK_POLICY_VERSION,
            "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
            "book_coverage": {
                "policy_version": CECCHINO_BOOK_POLICY_VERSION,
                "betfair_primary_selection_count": bf,
                "bet365_fallback_selection_count": b365,
                "missing_selection_count": missing,
                "bet365_fallback_fixture_count": int(self.bet365_fallback_fixture_count or 0),
                "book_coverage_fixture_count": fixture_count,
                "resolved_selection_count": resolved,
                "total_selection_count": total,
                "coverage_pct": coverage_pct,
                "selection_keys_count": selection_keys_count,
                "expected_selection_count": expected_selection_count,
                "actual_selection_count": actual_selection_count,
                "consistent": consistent,
            },
        }

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
        api_usage: dict[str, Any] | None = None,
        provider_items_received: int | None = None,
        provider_out_of_scan_date_skipped: int | None = None,
        fixtures_in_scan_date: int | None = None,
        out_of_scan_date_examples: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.sync_api_calls_total()
        summary: dict[str, Any] = {
            "fixtures_found": fixtures_found,
            "fixtures_censused": self.fixtures_censused,
            "after_competition_filter": after_competition_filter,
            "fixtures_after_competition_gate": self.fixtures_after_competition_gate,
            "fixtures_after_bookmaker_gate": self.fixtures_after_bookmaker_gate,
            "fixtures_after_stats_gate": self.fixtures_after_stats_gate,
            "odds_checked": odds_checked,
            "odds_from_cache": self.odds_from_cache,
            "odds_from_api": self.odds_from_api,
            "odds_cache_hits": self.odds_cache_hits,
            "negative_cache_hits": self.negative_cache_hits,
            "stats_checked": self.stats_checked,
            "bookmaker_fallback_count": self.bookmaker_fallback_count,
            "eligible_count": eligible_count,
            "excluded_count": excluded_count,
            "excluded_summary": dict(excluded_summary),
            "excluded_funnel": {
                "competition": sum(
                    excluded_summary.get(k, 0)
                    for k in (
                        "excluded_women",
                        "excluded_cup",
                        "excluded_friendly",
                        "excluded_youth",
                        "excluded_competition_type",
                        "excluded_started",
                    )
                ),
                "bookmaker": excluded_summary.get("excluded_missing_bookmaker", 0),
                "market_1x2": excluded_summary.get("excluded_missing_1x2_market", 0),
                "stats": excluded_summary.get("excluded_insufficient_stats", 0)
                + excluded_summary.get("excluded_leakage_failed", 0),
                "cecchino": sum(
                    excluded_summary.get(k, 0)
                    for k in (
                        "excluded_missing_picchetto",
                        "excluded_zero_probability",
                        "excluded_cecchino_not_calculable",
                        "excluded_kpi_not_calculable",
                    )
                ),
            },
            "api_calls": dict(self.api_calls),
            "api_calls_total": self.api_calls_total,
            "api_calls_by_endpoint": dict(self.api_calls),
            "odds_strategy": dict(self.odds_strategy),
            "duration_seconds": round(duration_seconds, 2),
            "api_usage": api_usage or {},
            "eligibility_transitions": dict(self.eligibility_transitions),
            "protected_eligible_total": int(self.protected_eligible_total),
            "protected_snapshot_overwrite_blocked": int(
                self.protected_snapshot_overwrite_blocked
            ),
            "snapshot_eligible_protection_active": True,
        }
        summary.update(self.book_coverage_fields())
        if provider_items_received is not None:
            summary["provider_items_received"] = provider_items_received
        if provider_out_of_scan_date_skipped is not None:
            summary["provider_out_of_scan_date_skipped"] = provider_out_of_scan_date_skipped
        if fixtures_in_scan_date is not None:
            summary["fixtures_in_scan_date"] = fixtures_in_scan_date
        if out_of_scan_date_examples:
            summary["out_of_scan_date_examples"] = out_of_scan_date_examples
        return summary
