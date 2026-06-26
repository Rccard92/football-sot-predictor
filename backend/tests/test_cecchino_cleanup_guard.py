"""Test guardie anti-cancellazione Cecchino Today — cleanup disabilitato di default."""

from __future__ import annotations

import os
from datetime import date, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.cecchino.cecchino_today_constants import CECCHINO_CLEANUP_CONFIRM_TOKEN
from app.services.cecchino.cecchino_recompute_service import recompute_today_fixture_offline
from app.services.cecchino.cecchino_today_service import (
    cleanup_cecchino_today_snapshots,
    list_available_days,
    revalidate_cecchino_today_day,
    run_scan,
)


def test_run_scan_does_not_call_cleanup():
    db = MagicMock()
    with (
        patch("app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots") as cleanup_mock,
        patch(
            "app.services.cecchino.cecchino_today_service.ApiFootballClient",
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.fetch_fixture_odds_for_cecchino_bookmakers",
            return_value=({}, []),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.get_api_usage_summary",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.sync_signals_for_scan_date",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.check_api_budget_during_scan",
        ),
        patch(
            "app.services.cecchino.cecchino_today_service._emit_progress",
        ),
        patch("app.services.cecchino.cecchino_today_service.ZoneInfo", return_value=timezone.utc),
    ):
        client = MagicMock()
        client.get_fixtures_by_date.return_value = []
        run_scan(db, scan_date=date(2026, 6, 4), client=client)
    cleanup_mock.assert_not_called()


def test_revalidate_does_not_call_cleanup():
    db = MagicMock()
    row = MagicMock()
    row.cecchino_output_json = {"final": {}, "warnings": []}
    row.eligibility_status = "eligible"
    row.stats_snapshot_json = {}
    row.warnings_json = []
    row.cecchino_status = "ok"
    db.scalars.return_value.all.return_value = [row]
    with patch(
        "app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots",
    ) as cleanup_mock, patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as val_mock:
        val_mock.return_value = MagicMock(
            is_eligible=True,
            eligibility_status="eligible",
            eligibility_reason="ok",
            blocking_reasons=[],
            warnings=[],
        )
        revalidate_cecchino_today_day(db, scan_date=date(2026, 6, 4))
    cleanup_mock.assert_not_called()


def test_recompute_does_not_delete_fixtures():
    db = MagicMock()
    row = MagicMock()
    row.id = 1
    row.local_fixture_id = 10
    row.competition_id = 1
    row.cecchino_output_json = {"final": {}, "warnings": []}
    row.stats_snapshot_json = {}
    row.odds_snapshot_json = {}
    row.warnings_json = []
    comp = MagicMock()
    fixture = MagicMock()
    db.get.side_effect = lambda model, pk: {1: comp, 10: fixture}.get(pk)

    with (
        patch(
            "app.services.cecchino.cecchino_recompute_service.calculate_and_persist_for_fixture",
            return_value={"status": "ok", "calculation_status": "ok", "output": {"final": {}, "warnings": []}},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.build_goal_market_contexts",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.build_goal_market_cecchino_odds",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.build_cecchino_kpi_panel_v2_betfair",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.validate_cecchino_today_final_eligibility",
        ) as val_mock,
        patch(
            "app.services.cecchino.cecchino_recompute_service._load_betfair_payload",
            return_value={"status": "ok"},
        ),
        patch(
            "app.services.cecchino.cecchino_recompute_service.read_odds_meta",
            return_value=None,
        ),
    ):
        val_mock.return_value = MagicMock(
            is_eligible=True,
            eligibility_status="eligible",
            eligibility_reason="ok",
            blocking_reasons=[],
            warnings=[],
        )
        recompute_today_fixture_offline(
            db,
            row,
            sync_signal_activations=False,
            evaluate_signals_after=False,
        )
    db.execute.assert_not_called()


def test_cleanup_dry_run_does_not_delete():
    db = MagicMock()
    db.scalar.return_value = 5
    with patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 26)):
        result = cleanup_cecchino_today_snapshots(db, dry_run=True)
    assert result["deleted"] == 0
    assert result["would_delete"] == 5
    assert result["dry_run"] is True
    db.execute.assert_not_called()


def test_cleanup_blocked_when_env_flag_false():
    db = MagicMock()
    db.scalar.return_value = 3
    settings = MagicMock()
    settings.cecchino_allow_destructive_cleanup = False
    with (
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 26)),
        patch("app.core.config.get_settings", return_value=settings),
    ):
        result = cleanup_cecchino_today_snapshots(
            db,
            dry_run=False,
            confirm=CECCHINO_CLEANUP_CONFIRM_TOKEN,
        )
    assert result["status"] == "blocked"
    assert result["reason"] == "env_flag_disabled"
    assert result["deleted"] == 0
    db.execute.assert_not_called()


def test_cleanup_blocked_when_confirm_missing():
    db = MagicMock()
    db.scalar.return_value = 2
    settings = MagicMock()
    settings.cecchino_allow_destructive_cleanup = True
    with (
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 26)),
        patch("app.core.config.get_settings", return_value=settings),
    ):
        result = cleanup_cecchino_today_snapshots(db, dry_run=False, confirm="wrong")
    assert result["status"] == "blocked"
    assert result["reason"] == "confirm_required"
    assert result["deleted"] == 0
    db.execute.assert_not_called()


def test_cleanup_deletes_only_when_all_gates_pass():
    db = MagicMock()
    db.scalar.return_value = 4
    mock_delete_result = MagicMock()
    mock_delete_result.rowcount = 4
    db.execute.return_value = mock_delete_result
    settings = MagicMock()
    settings.cecchino_allow_destructive_cleanup = True
    with (
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 26)),
        patch("app.core.config.get_settings", return_value=settings),
    ):
        result = cleanup_cecchino_today_snapshots(
            db,
            dry_run=False,
            confirm=CECCHINO_CLEANUP_CONFIRM_TOKEN,
            commit=True,
        )
    assert result["status"] == "ok"
    assert result["deleted"] == 4
    db.execute.assert_called_once()


def test_list_available_days_does_not_call_cleanup():
    db = MagicMock()
    with (
        patch("app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots") as cleanup_mock,
        patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 4)),
        patch("app.services.cecchino.cecchino_today_service.rome_tomorrow", return_value=date(2026, 6, 5)),
        patch("app.services.cecchino.cecchino_today_service._aggregate_scan_dates", return_value={}),
        patch("app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs"),
        patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_active_jobs_by_dates",
            return_value={},
        ),
        patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_latest_jobs_by_dates",
            return_value={},
        ),
    ):
        list_available_days(db)
    cleanup_mock.assert_not_called()


def test_signals_summary_reads_activations_without_delete():
    from app.services.cecchino.cecchino_signal_aggregation import build_signals_summary

    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = 0
    with patch(
        "app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots",
    ) as cleanup_mock:
        payload = build_signals_summary(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 26),
        )
    cleanup_mock.assert_not_called()
    assert "overall" in payload


def test_list_signal_activations_reads_without_delete():
    from app.services.cecchino.cecchino_signal_aggregation import list_signal_activations

    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch(
        "app.services.cecchino.cecchino_today_service.cleanup_cecchino_today_snapshots",
    ) as cleanup_mock:
        rows = list_signal_activations(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 26),
        )
    cleanup_mock.assert_not_called()
    assert "items" in rows
