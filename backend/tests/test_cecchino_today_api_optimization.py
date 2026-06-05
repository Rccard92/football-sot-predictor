"""Test Fase 19 — gate progressivi e ottimizzazione API Cecchino Today."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_fixture import ELIGIBILITY_DISCOVERED, ELIGIBILITY_EXCLUDED_CUP
from app.models.cecchino_today_scan_job import (
    JOB_STATUS_FAILED_BUDGET_GUARD,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
)
from app.services.api_usage_context import BudgetGuardStop
from app.services.api_usage_service import (
    check_api_budget_before_scan,
    check_api_budget_during_scan,
    record_api_usage_event,
)
from app.services.cecchino.cecchino_today_odds_fetch import (
    check_negative_odds_cache,
    fetch_fixture_odds_for_cecchino_bookmakers,
    load_cached_odds_for_fixture,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics
from app.services.cecchino.cecchino_today_service import (
    revalidate_cecchino_today_day,
    run_scan,
    update_today_fixture_results,
)
from app.services.api_usage_context import ApiUsageContext

TARGET_DATE = date(2026, 6, 5)


def _api_fixture(api_fid: int, league_name: str = "Serie A") -> dict:
    return {
        "fixture": {"id": api_fid, "date": "2026-06-05T18:00:00+00:00", "status": {"short": "NS"}},
        "league": {"id": 135, "name": league_name, "country": "Italy", "season": 2025, "logo": ""},
        "teams": {
            "home": {"name": "Home", "logo": ""},
            "away": {"name": "Away", "logo": ""},
        },
    }


def test_scan_run_census_discovered_status():
    db = MagicMock()
    db.commit = MagicMock()
    db.scalar = MagicMock(return_value=None)
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [_api_fixture(1), _api_fixture(2)]
    upserts: list[str] = []

    def _track_upsert(*_a, **kw):
        upserts.append(kw.get("eligibility_status", ""))
        return MagicMock()

    with patch("app.services.cecchino.cecchino_today_service._upsert_today_snapshot", side_effect=_track_upsert):
        with patch("app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots", return_value={}):
            with patch("app.services.cecchino.cecchino_today_service.get_api_usage_summary", return_value={"total_calls": 1}):
                with patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=timezone.utc):
                    with patch(
                        "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
                        return_value=(False, ELIGIBILITY_EXCLUDED_CUP),
                    ):
                        with patch("app.services.cecchino.cecchino_today_service.check_api_budget_during_scan"):
                            report = run_scan(db, scan_date=TARGET_DATE, client=client, force_rescan=True)

    assert report["status"] == "ok"
    assert upserts[:2] == [ELIGIBILITY_DISCOVERED, ELIGIBILITY_DISCOVERED]


def test_competition_gate_excludes_without_odds_api():
    db = MagicMock()
    db.commit = MagicMock()
    db.scalar = MagicMock(return_value=None)
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [_api_fixture(99, "FA Cup")]
    odds_fetch = MagicMock()

    with patch("app.services.cecchino.cecchino_today_service._upsert_today_snapshot", return_value=MagicMock()):
        with patch("app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots", return_value={}):
            with patch("app.services.cecchino.cecchino_today_service.get_api_usage_summary", return_value={"total_calls": 1}):
                with patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=timezone.utc):
                    with patch(
                        "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
                        return_value=(False, ELIGIBILITY_EXCLUDED_CUP),
                    ):
                        with patch("app.services.cecchino.cecchino_today_service.check_api_budget_during_scan"):
                            with patch(
                                "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
                                odds_fetch,
                            ):
                                run_scan(db, scan_date=TARGET_DATE, client=client, force_rescan=True)

    odds_fetch.assert_not_called()


def test_bookmaker_gate_fail_skips_bootstrap():
    db = MagicMock()
    db.commit = MagicMock()
    db.scalar = MagicMock(return_value=None)
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [_api_fixture(10)]
    bootstrap = MagicMock()

    with patch("app.services.cecchino.cecchino_today_service._upsert_today_snapshot", return_value=MagicMock()):
        with patch("app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots", return_value={}):
            with patch("app.services.cecchino.cecchino_today_service.get_api_usage_summary", return_value={"total_calls": 2}):
                with patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=timezone.utc):
                    with patch(
                        "app.services.cecchino.cecchino_today_service.is_cecchino_allowed_competition",
                        return_value=(True, None),
                    ):
                        with patch(
                            "app.services.cecchino.cecchino_today_service.is_fixture_not_started",
                            return_value=True,
                        ):
                            with patch("app.services.cecchino.cecchino_today_service.check_api_budget_during_scan"):
                                with patch(
                                    "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
                                    return_value=({}, [], "fixture_single_call", False),
                                ):
                                    with patch(
                                        "app.services.cecchino.cecchino_today_service.verify_complete_1x2_odds",
                                        return_value=(False, {}, "missing_bookmaker", ["missing_bookmaker:Bet365"]),
                                    ):
                                        with patch(
                                            "app.services.cecchino.cecchino_today_service.ensure_competition_and_history",
                                            bootstrap,
                                        ):
                                            run_scan(db, scan_date=TARGET_DATE, client=client, force_rescan=True)

    bootstrap.assert_not_called()


def test_odds_cache_skips_api_call():
    db = MagicMock()
    row = MagicMock()
    row.negative_cache_until = None
    db.scalar = MagicMock(return_value=row)
    client = MagicMock()
    metrics = ScanRunMetrics()
    cached = {8: [{"bookmakers": []}], 3: [{"bookmakers": []}], 4: [{"bookmakers": []}]}

    with patch(
        "app.services.cecchino.cecchino_today_odds_fetch.load_cached_odds_for_fixture",
        return_value=cached,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_odds_fetch._book_ids_complete",
            return_value=True,
        ):
            odds, _w, strategy, neg = fetch_fixture_odds_for_cecchino_bookmakers(
                client,
                123,
                db=db,
                scan_date=TARGET_DATE,
                metrics=metrics,
            )

    assert strategy == "cached"
    assert neg is False
    client.get_fixture_odds_by_fixture.assert_not_called()
    assert metrics.odds_cache_hits == 1


def test_negative_cache_skips_api_call():
    db = MagicMock()
    row = MagicMock()
    row.negative_cache_until = datetime.now(timezone.utc) + timedelta(hours=1)
    row.odds_check_status = "missing_bookmaker"
    db.scalar = MagicMock(return_value=row)
    client = MagicMock()
    metrics = ScanRunMetrics()

    odds, warnings, strategy, neg = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        456,
        db=db,
        scan_date=TARGET_DATE,
        metrics=metrics,
    )

    assert neg is True
    assert strategy == "negative_cache"
    assert metrics.negative_cache_hits == 1
    client.get_fixture_odds_by_fixture.assert_not_called()


def test_revalidate_day_does_not_use_api_client():
    db = MagicMock()
    row = MagicMock()
    row.eligibility_status = "eligible"
    row.cecchino_output_json = {"final": {"quota_1": 2.0}}
    row.stats_snapshot_json = {}
    row.odds_snapshot_json = {}
    row.kpi_panel_json = {}
    row.warnings_json = []
    row.cecchino_status = "ok"
    db.scalars.return_value.all.return_value = [row]
    client = MagicMock()

    with patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as mock_val:
        mock_val.return_value = MagicMock(
            eligibility_status="eligible",
            eligibility_reason=None,
            blocking_reasons=[],
            warnings=[],
            is_eligible=True,
        )
        revalidate_cecchino_today_day(db, scan_date=TARGET_DATE)

    client.get.assert_not_called()


def test_update_results_uses_date_level_fetch():
    db = MagicMock()
    row = MagicMock()
    row.provider_fixture_id = 100
    db.scalars.return_value.all.return_value = [row]
    client = MagicMock()
    client.get_fixtures_by_date.return_value = [_api_fixture(100)]

    with patch("app.services.cecchino.cecchino_today_service.apply_display_from_api"):
        with patch(
            "app.services.cecchino.cecchino_today_service._resolve_row_match_status",
            return_value="upcoming",
        ):
            result = update_today_fixture_results(db, scan_date=TARGET_DATE, client=client)

    assert result["api_calls"] == 1
    client.get_fixtures_by_date.assert_called_once()
    client.get_fixture_by_id.assert_not_called()


def test_api_usage_event_recorded():
    db = MagicMock()
    record_api_usage_event(
        db,
        endpoint="odds",
        params={"fixture": 1},
        status_code=200,
        duration_ms=50,
        job_id="jid",
        scan_date=TARGET_DATE,
    )
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_budget_guard_before_scan():
    db = MagicMock()
    with patch("app.services.api_usage_service.count_api_calls_for_date", return_value=7100):
        with pytest.raises(BudgetGuardStop) as exc:
            check_api_budget_before_scan(db, usage_date=TARGET_DATE)
    assert exc.value.status == JOB_STATUS_FAILED_BUDGET_GUARD


def test_budget_guard_during_scan_job_max():
    db = MagicMock()
    with patch("app.services.api_usage_service.count_api_calls_for_date", return_value=100):
        with pytest.raises(BudgetGuardStop) as exc:
            check_api_budget_during_scan(
                db,
                job_id="jid",
                usage_date=TARGET_DATE,
                job_calls=1000,
            )
    assert exc.value.status == JOB_STATUS_PARTIAL_STOPPED_BUDGET


def test_scan_metrics_result_summary_funnel():
    metrics = ScanRunMetrics()
    metrics.fixtures_censused = 10
    metrics.fixtures_after_competition_gate = 6
    metrics.fixtures_after_bookmaker_gate = 4
    metrics.fixtures_after_stats_gate = 3
    metrics.api_calls = {"odds": 5, "fixtures": 1, "teams": 2}
    summary = metrics.to_result_summary(
        fixtures_found=10,
        after_competition_filter=6,
        odds_checked=6,
        eligible_count=2,
        excluded_count=8,
        excluded_summary={"excluded_cup": 4, "excluded_missing_bookmaker": 2},
        duration_seconds=12.5,
        api_usage={"total_calls": 8, "estimated_remaining_daily_budget": 7492},
    )
    assert summary["fixtures_censused"] == 10
    assert summary["api_calls_total"] == 8
    assert summary["api_usage"]["estimated_remaining_daily_budget"] == 7492
    assert "excluded_funnel" in summary
