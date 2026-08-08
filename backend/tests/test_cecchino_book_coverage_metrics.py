"""Test metriche diagnostiche Book coverage (CECCHINO-BOOK-MONITOR-01)."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_scan_job import JOB_STATUS_RUNNING, CecchinoTodayScanJob
from app.services.cecchino.cecchino_constants import CECCHINO_BOOK_POLICY_VERSION
from app.services.cecchino.cecchino_today_odds_fetch import (
    _BET365_ID,
    _BETFAIR_ID,
    _record_resolution_metrics,
    fetch_fixture_odds_for_cecchino_bookmakers,
)
from app.services.cecchino.cecchino_today_scan_job_service import make_progress_reporter
from app.services.cecchino.cecchino_today_scan_metrics import (
    ScanRunMetrics,
    book_coverage_integrity_warning,
)
from app.services.cecchino.cecchino_canonical_book_resolver import (
    CANONICAL_BOOK_SELECTION_KEYS,
)


def _book_raw(
    *,
    bookmaker_id: int,
    bookmaker_name: str,
    match_winner: dict[str, str] | None = None,
    over_under: dict[str, str] | None = None,
    double_chance: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    if match_winner:
        bets.append(
            {
                "id": 1,
                "name": "Match Winner",
                "values": [{"value": k, "odd": v} for k, v in match_winner.items()],
            },
        )
    if over_under:
        bets.append(
            {
                "id": 5,
                "name": "Goals Over/Under",
                "values": [{"value": k, "odd": v} for k, v in over_under.items()],
            },
        )
    if double_chance:
        bets.append(
            {
                "id": 12,
                "name": "Double Chance",
                "values": [{"value": k, "odd": v} for k, v in double_chance.items()],
            },
        )
    return [
        {
            "bookmakers": [
                {
                    "id": bookmaker_id,
                    "name": bookmaker_name,
                    "bets": bets,
                },
            ],
        },
    ]


def _stats(
    *,
    bf: int,
    b365: int,
    missing: int,
) -> dict[str, Any]:
    return {
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "betfair_primary_used": bf > 0,
        "bet365_fallback_used": b365 > 0,
        "betfair_primary_selection_count": bf,
        "bet365_fallback_selection_count": b365,
        "book_still_missing_after_fallback": missing,
    }


def test_book_coverage_10_bf_3_b365_2_missing():
    metrics = ScanRunMetrics()
    with patch(
        "app.services.cecchino.cecchino_today_odds_fetch._build_resolved",
        return_value=({}, {}, _stats(bf=10, b365=3, missing=2)),
    ):
        _record_resolution_metrics(metrics, {_BETFAIR_ID: []})

    assert metrics.betfair_primary_selection_count == 10
    assert metrics.bet365_fallback_selection_count == 3
    assert metrics.book_still_missing_after_fallback == 2
    assert metrics.betfair_primary_used == 1
    assert metrics.bet365_fallback_used == 1
    assert metrics.bet365_fallback_fixture_count == 1

    fields = metrics.book_coverage_fields()
    assert fields["book_coverage"]["resolved_selection_count"] == 13
    assert fields["book_coverage"]["total_selection_count"] == 15
    assert fields["book_coverage_pct"] == 86.7
    assert fields["book_coverage"]["coverage_pct"] == 86.7


def test_book_coverage_accumulates_two_fixtures():
    metrics = ScanRunMetrics()
    with patch(
        "app.services.cecchino.cecchino_today_odds_fetch._build_resolved",
        side_effect=[
            ({}, {}, _stats(bf=10, b365=3, missing=2)),
            ({}, {}, _stats(bf=5, b365=1, missing=0)),
        ],
    ):
        _record_resolution_metrics(metrics, {_BETFAIR_ID: []})
        _record_resolution_metrics(metrics, {_BETFAIR_ID: []})

    assert metrics.betfair_primary_selection_count == 15
    assert metrics.bet365_fallback_selection_count == 4
    assert metrics.book_still_missing_after_fallback == 2
    assert metrics.betfair_primary_used == 2
    assert metrics.bet365_fallback_fixture_count == 2
    fields = metrics.book_coverage_fields()
    # resolved=19, total=21 → 90.476… → 90.5
    assert fields["book_coverage_pct"] == 90.5


def test_recovery_betfair_specific_no_double_count(monkeypatch):
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    client = MagicMock()
    # Fixture-wide incompleto (solo Home) → trigger Betfair-specific recovery
    fixture_wide = [
        {
            "bookmakers": [
                {
                    "id": _BETFAIR_ID,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [{"value": "Home", "odd": "1.8"}],
                        },
                    ],
                },
            ],
        },
    ]
    betfair_specific = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.8", "Draw": "3.2", "Away": "4.5"},
        over_under={"Over 2.5": "1.9", "Under 2.5": "1.9"},
    )
    client.get_fixture_odds_by_fixture.return_value = fixture_wide
    client.get_fixture_odds.return_value = betfair_specific

    metrics = ScanRunMetrics()
    odds, _, strategy, _ = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        101,
        force_rescan=True,
        metrics=metrics,
    )
    assert _BETFAIR_ID in odds
    assert client.get_fixture_odds.call_count >= 1
    # Una sola registrazione finale: selection count == resolve una volta
    with patch(
        "app.services.cecchino.cecchino_today_odds_fetch._build_resolved",
        wraps=__import__(
            "app.services.cecchino.cecchino_today_odds_fetch",
            fromlist=["_build_resolved"],
        )._build_resolved,
    ) as _:
        pass
    # Re-resolve finale e confronta (niente doppio)
    from app.services.cecchino.cecchino_today_odds_fetch import _build_resolved

    _, _, final_stats = _build_resolved(odds)
    assert metrics.betfair_primary_selection_count == int(
        final_stats["betfair_primary_selection_count"],
    )
    assert metrics.bet365_fallback_selection_count == int(
        final_stats["bet365_fallback_selection_count"],
    )
    assert metrics.book_still_missing_after_fallback == int(
        final_stats["book_still_missing_after_fallback"],
    )
    assert metrics.betfair_primary_used == (1 if final_stats["betfair_primary_used"] else 0)


def test_recovery_bet365_specific_no_double_count(monkeypatch):
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    client = MagicMock()
    fixture_wide = [
        {
            "bookmakers": [
                {
                    "id": _BETFAIR_ID,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.8"},
                                {"value": "Draw", "odd": "3.2"},
                                {"value": "Away", "odd": "4.5"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    betfair_specific = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.8", "Draw": "3.2", "Away": "4.5"},
    )
    bet365_specific = _book_raw(
        bookmaker_id=_BET365_ID,
        bookmaker_name="Bet365",
        over_under={"Over 2.5": "1.36", "Under 2.5": "3.00"},
    )
    client.get_fixture_odds_by_fixture.return_value = fixture_wide

    def _get_odds(_fid, bookmaker_id):
        if bookmaker_id == _BETFAIR_ID:
            return betfair_specific
        return bet365_specific

    client.get_fixture_odds.side_effect = _get_odds
    metrics = ScanRunMetrics()
    odds, _, strategy, _ = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        42,
        force_rescan=True,
        metrics=metrics,
    )
    assert "bet365" in strategy
    assert client.get_fixture_odds.call_count == 2

    from app.services.cecchino.cecchino_today_odds_fetch import _build_resolved

    _, _, final_stats = _build_resolved(odds)
    assert metrics.betfair_primary_selection_count == int(
        final_stats["betfair_primary_selection_count"],
    )
    assert metrics.bet365_fallback_selection_count == int(
        final_stats["bet365_fallback_selection_count"],
    )
    assert metrics.bet365_fallback_fixture_count == (
        1 if final_stats["bet365_fallback_used"] else 0
    )
    # Non raddoppiato nonostante 2 recovery call
    assert metrics.bet365_fallback_selection_count == final_stats[
        "bet365_fallback_selection_count"
    ]


def test_cache_metrics_match_snapshot_provenance(monkeypatch):
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    cached = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.9", "Draw": "3.3", "Away": "4.0"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            over_under={"Over 2.5": "1.7", "Under 2.5": "2.1"},
            double_chance={"Home/Draw": "1.2", "Draw/Away": "1.9", "Home/Away": "1.4"},
        ),
    }
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.check_negative_odds_cache",
        lambda *_a, **_k: (False, None, None),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.load_cached_odds_for_fixture",
        lambda *_a, **_k: cached,
    )
    client = MagicMock()
    metrics = ScanRunMetrics()
    odds, _, strategy, neg = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        55,
        db=MagicMock(),
        scan_date=date(2026, 8, 8),
        force_rescan=False,
        metrics=metrics,
    )
    assert strategy == "cached"
    assert neg is False
    client.get_fixture_odds_by_fixture.assert_not_called()

    from app.services.cecchino.cecchino_today_odds_fetch import _build_resolved

    _, _, final_stats = _build_resolved(odds)
    assert metrics.betfair_primary_selection_count == int(
        final_stats["betfair_primary_selection_count"],
    )
    assert metrics.bet365_fallback_selection_count == int(
        final_stats["bet365_fallback_selection_count"],
    )
    assert metrics.book_still_missing_after_fallback == int(
        final_stats["book_still_missing_after_fallback"],
    )
    assert metrics.bet365_fallback_fixture_count == (
        1 if final_stats["bet365_fallback_used"] else 0
    )


def test_zero_quotes_coverage_null():
    metrics = ScanRunMetrics()
    fields = metrics.book_coverage_fields()
    assert fields["book_coverage_pct"] is None
    assert fields["book_coverage"]["coverage_pct"] is None
    assert fields["book_coverage"]["total_selection_count"] == 0
    summary = metrics.to_result_summary(
        fixtures_found=0,
        after_competition_filter=0,
        odds_checked=0,
        eligible_count=0,
        excluded_count=0,
        excluded_summary={},
        duration_seconds=0.0,
    )
    assert summary["book_coverage_pct"] is None
    assert "betfair_primary_selection_count" in summary


def test_progress_reporter_merges_book_coverage_live():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="jid-book",
        scan_date=date(2026, 8, 8),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=1,
        progress_total=10,
        progress_pct=Decimal("10.0"),
        result_summary_json={
            "scan_date": "2026-08-08",
            "execution_date": "2026-08-08",
            "auto_scan": {"execution_source": "auto_scan", "attempt": 1},
        },
    )
    metrics = ScanRunMetrics()
    metrics.betfair_primary_selection_count = 10
    metrics.bet365_fallback_selection_count = 3
    metrics.book_still_missing_after_fallback = 2
    metrics.bet365_fallback_fixture_count = 1
    metrics.betfair_primary_used = 1
    metrics.bet365_fallback_used = 1
    patch_fields = metrics.book_coverage_fields()

    captured: dict[str, Any] = {}

    def _fake_update(_db, _jid, **kwargs):
        captured.update(kwargs)
        if "result_summary_json" in kwargs:
            job.result_summary_json = kwargs["result_summary_json"]
        return job

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
        return_value=job,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.update_scan_job",
            side_effect=_fake_update,
        ):
            reporter = make_progress_reporter(db, "jid-book")
            reporter(
                progress_current=2,
                progress_total=10,
                result_summary_json=patch_fields,
            )

    merged = captured["result_summary_json"]
    assert merged["auto_scan"]["execution_source"] == "auto_scan"
    assert merged["scan_date"] == "2026-08-08"
    assert merged["execution_date"] == "2026-08-08"
    assert merged["betfair_primary_selection_count"] == 10
    assert merged["bet365_fallback_selection_count"] == 3
    assert merged["book_still_missing_after_fallback"] == 2
    assert merged["bet365_fallback_fixture_count"] == 1
    assert merged["book_coverage_pct"] == 86.7
    assert merged["book_coverage"]["coverage_pct"] == 86.7


def test_progress_reporter_merges_live_api_metrics():
    """Live polling deve ricevere api_calls / odds_from_api in result_summary."""
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="jid-api",
        scan_date=date(2026, 8, 8),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=1,
        progress_total=10,
        progress_pct=Decimal("10.0"),
        result_summary_json={
            "auto_scan": {"execution_source": "auto_scan"},
            "execution_date": "2026-08-08",
        },
    )
    metrics = ScanRunMetrics()
    metrics.api_calls = {"odds": 123, "fixtures": 2, "teams": 0}
    metrics.sync_api_calls_total()
    metrics.odds_from_api = 40
    metrics.odds_from_cache = 5
    metrics.odds_cache_hits = 5
    metrics.negative_cache_hits = 1
    metrics.odds_strategy["betfair_1x2"] = 30
    live = {
        "api_calls": dict(metrics.api_calls),
        "api_calls_total": metrics.api_calls_total,
        "odds_from_api": metrics.odds_from_api,
        "odds_from_cache": metrics.odds_from_cache,
        "odds_cache_hits": metrics.odds_cache_hits,
        "negative_cache_hits": metrics.negative_cache_hits,
        "odds_strategy": dict(metrics.odds_strategy),
    }
    live.update(metrics.book_coverage_fields())
    captured: dict[str, Any] = {}

    def _fake_update(_db, _jid, **kwargs):
        captured.update(kwargs)
        if "result_summary_json" in kwargs:
            job.result_summary_json = kwargs["result_summary_json"]
        return job

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
        return_value=job,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.update_scan_job",
            side_effect=_fake_update,
        ):
            reporter = make_progress_reporter(db, "jid-api")
            reporter(progress_current=2, result_summary_json=live)

    merged = captured["result_summary_json"]
    assert merged["api_calls"]["odds"] == 123
    assert merged["api_calls_total"] == 125
    assert merged["odds_from_api"] == 40
    assert merged["odds_cache_hits"] == 5
    assert merged["auto_scan"]["execution_source"] == "auto_scan"
    assert merged["execution_date"] == "2026-08-08"


def test_completed_summary_includes_final_book_coverage():
    metrics = ScanRunMetrics()
    metrics.betfair_primary_selection_count = 10
    metrics.bet365_fallback_selection_count = 3
    metrics.book_still_missing_after_fallback = 2
    metrics.bet365_fallback_fixture_count = 1
    metrics.betfair_primary_used = 1
    metrics.bet365_fallback_used = 1
    metrics.book_coverage_fixture_count = 2
    summary = metrics.to_result_summary(
        fixtures_found=5,
        after_competition_filter=4,
        odds_checked=2,
        eligible_count=1,
        excluded_count=1,
        excluded_summary={"excluded_missing_bookmaker": 1},
        duration_seconds=12.3,
    )
    assert summary["betfair_primary_selection_count"] == 10
    assert summary["bet365_fallback_selection_count"] == 3
    assert summary["book_still_missing_after_fallback"] == 2
    assert summary["bet365_fallback_fixture_count"] == 1
    assert summary["book_coverage_fixture_count"] == 2
    assert summary["book_coverage_pct"] == 86.7
    assert summary["book_coverage"]["policy_version"] == CECCHINO_BOOK_POLICY_VERSION
    assert summary["book_coverage"]["book_coverage_fixture_count"] == 2
    assert summary["book_policy_version"] == CECCHINO_BOOK_POLICY_VERSION


def test_legacy_summary_without_book_fields_is_safe():
    # Consumer che legge solo campi legacy non crasha
    legacy = {
        "fixtures_found": 3,
        "api_calls_total": 10,
        "scan_date": "2026-08-01",
    }
    assert legacy.get("betfair_primary_selection_count") is None
    assert legacy.get("book_coverage_pct") is None
    assert legacy.get("book_coverage") is None
    # book_coverage_fields su metrics vuote resta backward-compatible (null coverage)
    empty = ScanRunMetrics().book_coverage_fields()
    assert empty["book_coverage_pct"] is None
    assert empty["betfair_primary_selection_count"] == 0


def test_integrity_consistent_120_fixtures_case_a():
    """A) 120 fixture × 19 keys, BF+B365+missing = expected → consistent."""
    metrics = ScanRunMetrics()
    metrics.book_coverage_fixture_count = 120
    metrics.betfair_primary_selection_count = 1850
    metrics.bet365_fallback_selection_count = 170
    metrics.book_still_missing_after_fallback = 260
    fields = metrics.book_coverage_fields()
    keys = len(CANONICAL_BOOK_SELECTION_KEYS)
    assert keys == 19
    assert fields["book_selection_keys_count"] == keys
    assert fields["book_coverage_expected_selection_count"] == 2280
    assert fields["book_coverage_actual_selection_count"] == 2280
    assert fields["book_coverage_consistent"] is True
    assert fields["book_coverage"]["selection_keys_count"] == keys
    assert fields["book_coverage"]["expected_selection_count"] == 2280
    assert fields["book_coverage"]["actual_selection_count"] == 2280
    assert fields["book_coverage"]["consistent"] is True
    assert book_coverage_integrity_warning(fields) is None


def test_integrity_inconsistent_production_case_b():
    """B) Replica caso produzione: actual >> expected → inconsistent + warning."""
    metrics = ScanRunMetrics()
    metrics.book_coverage_fixture_count = 120
    metrics.betfair_primary_selection_count = 0
    metrics.bet365_fallback_selection_count = 610
    metrics.book_still_missing_after_fallback = 3561
    fields = metrics.book_coverage_fields()
    assert fields["book_coverage_expected_selection_count"] == 2280
    assert fields["book_coverage_actual_selection_count"] == 4171
    assert fields["book_coverage_consistent"] is False
    assert fields["book_coverage"]["consistent"] is False
    # Raw counters preservati (no clamp)
    assert fields["betfair_primary_selection_count"] == 0
    assert fields["bet365_fallback_selection_count"] == 610
    assert fields["book_still_missing_after_fallback"] == 3561
    warn = book_coverage_integrity_warning(fields)
    assert warn is not None
    assert warn.startswith("book_coverage_counter_mismatch")
    assert "fixtures=120" in warn
    assert "selection_keys_count=19" in warn
    assert "expected=2280" in warn
    assert "actual=4171" in warn
    assert "BF=0" in warn
    assert "B365=610" in warn
    assert "missing=3561" in warn


def test_integrity_fixture_count_zero_no_false_warning_case_c():
    """C) fixture_count=0 → consistent (0==0), nessun warning."""
    fields = ScanRunMetrics().book_coverage_fields()
    assert fields["book_coverage_fixture_count"] == 0
    assert fields["book_coverage_expected_selection_count"] == 0
    assert fields["book_coverage_actual_selection_count"] == 0
    assert fields["book_coverage_consistent"] is True
    assert book_coverage_integrity_warning(fields) is None


def test_integrity_does_not_mutate_counters_case_d():
    """D) book_coverage_fields non altera i counters sullo ScanRunMetrics."""
    metrics = ScanRunMetrics()
    metrics.book_coverage_fixture_count = 120
    metrics.betfair_primary_selection_count = 0
    metrics.bet365_fallback_selection_count = 610
    metrics.book_still_missing_after_fallback = 3561
    before = (
        metrics.betfair_primary_selection_count,
        metrics.bet365_fallback_selection_count,
        metrics.book_still_missing_after_fallback,
        metrics.book_coverage_fixture_count,
    )
    fields = metrics.book_coverage_fields()
    after = (
        metrics.betfair_primary_selection_count,
        metrics.bet365_fallback_selection_count,
        metrics.book_still_missing_after_fallback,
        metrics.book_coverage_fixture_count,
    )
    assert before == after
    assert fields["betfair_primary_selection_count"] == 0
    assert fields["bet365_fallback_selection_count"] == 610
    assert fields["book_still_missing_after_fallback"] == 3561
    # coverage_pct raw ancora derivato da resolved/total (non azzerato)
    assert fields["book_coverage_pct"] == round(610 / 4171 * 100, 1)
