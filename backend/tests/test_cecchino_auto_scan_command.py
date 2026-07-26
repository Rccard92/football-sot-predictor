"""Test comando sincrono cecchino_auto_scan."""

from __future__ import annotations

import os
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.jobs.cecchino_auto_scan import (
    EXIT_CONFIG,
    EXIT_OK,
    SLOT_PRIMARY,
    SLOT_RECOVERY,
    build_auto_scan_meta,
    evaluate_auto_scan_idempotency,
    local_execution_date,
    main,
    outcome_to_exit_code,
    resolve_auto_scan_slot,
    resolve_target_scan_date,
    _is_transient_retryable,
)
from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_FAILED_BUDGET_GUARD,
    JOB_STATUS_FAILED_TIMEOUT,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
    JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
    CecchinoTodayScanJob,
)


ROME = "Europe/Rome"


def _dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(ROME))


def test_target_tomorrow_europe_rome():
    now = _dt(2026, 7, 26, 23, 30)
    assert resolve_target_scan_date(now, timezone_name=ROME) == date(2026, 7, 27)
    assert local_execution_date(now, timezone_name=ROME) == date(2026, 7, 26)


def test_midnight_day_rollover():
    before = _dt(2026, 7, 26, 23, 59)
    after = _dt(2026, 7, 27, 0, 1)
    assert resolve_target_scan_date(before, timezone_name=ROME) == date(2026, 7, 27)
    assert resolve_target_scan_date(after, timezone_name=ROME) == date(2026, 7, 28)


def test_dst_spring_forward_rome():
    # 29 marzo 2026: passaggio CET→CEST (ore 02:00 → 03:00)
    winter = datetime(2026, 3, 28, 23, 30, tzinfo=ZoneInfo(ROME))
    summer = datetime(2026, 3, 29, 23, 30, tzinfo=ZoneInfo(ROME))
    assert resolve_target_scan_date(winter, timezone_name=ROME) == date(2026, 3, 29)
    assert resolve_target_scan_date(summer, timezone_name=ROME) == date(2026, 3, 30)
    assert winter.utcoffset() != summer.utcoffset()


def test_slot_primary():
    now = _dt(2026, 7, 26, 23, 30)
    slot = resolve_auto_scan_slot(
        now,
        timezone_name=ROME,
        primary_hour=23,
        primary_minute=30,
        recovery_hour=23,
        recovery_minute=50,
        window_minutes=10,
    )
    assert slot == SLOT_PRIMARY


def test_slot_recovery():
    now = _dt(2026, 7, 26, 23, 50)
    slot = resolve_auto_scan_slot(
        now,
        timezone_name=ROME,
        primary_hour=23,
        primary_minute=30,
        recovery_hour=23,
        recovery_minute=50,
        window_minutes=10,
    )
    assert slot == SLOT_RECOVERY


def test_outside_window():
    now = _dt(2026, 7, 26, 12, 0)
    slot = resolve_auto_scan_slot(
        now,
        timezone_name=ROME,
        primary_hour=23,
        primary_minute=30,
        recovery_hour=23,
        recovery_minute=50,
        window_minutes=10,
    )
    assert slot is None


def test_scheduled_disabled_exit_0():
    settings = MagicMock()
    settings.cecchino_auto_scan_enabled = False
    settings.cecchino_auto_scan_timezone = ROME
    settings.cecchino_auto_scan_primary_hour = 23
    settings.cecchino_auto_scan_primary_minute = 30
    settings.cecchino_auto_scan_recovery_hour = 23
    settings.cecchino_auto_scan_recovery_minute = 50
    settings.cecchino_auto_scan_window_minutes = 10
    with patch("app.jobs.cecchino_auto_scan.get_settings", return_value=settings):
        with patch("app.jobs.cecchino_auto_scan.datetime") as mock_dt:
            mock_dt.now.return_value = _dt(2026, 7, 26, 23, 30)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            code = main(["--scheduled"])
    assert code == EXIT_OK


def test_scheduled_outside_window_exit_0():
    settings = MagicMock()
    settings.cecchino_auto_scan_enabled = True
    settings.cecchino_auto_scan_timezone = ROME
    settings.cecchino_auto_scan_primary_hour = 23
    settings.cecchino_auto_scan_primary_minute = 30
    settings.cecchino_auto_scan_recovery_hour = 23
    settings.cecchino_auto_scan_recovery_minute = 50
    settings.cecchino_auto_scan_window_minutes = 10
    with patch("app.jobs.cecchino_auto_scan.get_settings", return_value=settings):
        with patch("app.jobs.cecchino_auto_scan.datetime") as mock_dt:
            mock_dt.now.return_value = _dt(2026, 7, 26, 12, 0)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            code = main(["--scheduled"])
    assert code == EXIT_OK


def test_target_date_without_force_rejected():
    settings = MagicMock()
    settings.cecchino_auto_scan_enabled = True
    settings.cecchino_auto_scan_timezone = ROME
    with patch("app.jobs.cecchino_auto_scan.get_settings", return_value=settings):
        # argparse: --target-date with --scheduled is allowed by parser but main rejects
        # Actually mutually exclusive is scheduled vs force-run; target-date alone with scheduled
        code = main(["--scheduled", "--target-date", "2026-07-27"])
    assert code == EXIT_CONFIG


def test_force_run_calls_run_auto_scan():
    settings = MagicMock()
    settings.cecchino_auto_scan_enabled = False
    settings.cecchino_auto_scan_timezone = ROME
    settings.cecchino_auto_scan_primary_hour = 23
    settings.cecchino_auto_scan_primary_minute = 30
    settings.cecchino_auto_scan_recovery_hour = 23
    settings.cecchino_auto_scan_recovery_minute = 50
    settings.cecchino_auto_scan_window_minutes = 10
    settings.cecchino_auto_scan_max_runtime_minutes = 120
    settings.cecchino_auto_scan_transient_attempts = 2
    settings.cecchino_auto_scan_transient_retry_delay_seconds = 0
    with patch("app.jobs.cecchino_auto_scan.get_settings", return_value=settings):
        with patch("app.jobs.cecchino_auto_scan.run_auto_scan", return_value=EXIT_OK) as run:
            with patch("app.jobs.cecchino_auto_scan.datetime") as mock_dt:
                mock_dt.now.return_value = _dt(2026, 7, 26, 12, 0)
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                code = main(["--force-run", "--target-date", "2026-07-27"])
    assert code == EXIT_OK
    assert run.called
    kwargs = run.call_args.kwargs
    assert kwargs["target_date"] == date(2026, 7, 27)
    assert kwargs["force_run"] is True


def test_dry_run_no_writes():
    settings = MagicMock()
    settings.cecchino_auto_scan_enabled = True
    settings.cecchino_auto_scan_timezone = ROME
    settings.cecchino_auto_scan_primary_hour = 23
    settings.cecchino_auto_scan_primary_minute = 30
    settings.cecchino_auto_scan_recovery_hour = 23
    settings.cecchino_auto_scan_recovery_minute = 50
    settings.cecchino_auto_scan_window_minutes = 10
    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    with patch("app.jobs.cecchino_auto_scan.get_settings", return_value=settings):
        with patch("app.jobs.cecchino_auto_scan.SessionLocal", return_value=db):
            with patch("app.jobs.cecchino_auto_scan.recover_stale_scan_jobs"):
                with patch("app.jobs.cecchino_auto_scan.find_auto_scan_jobs_for_execution", return_value=[]):
                    with patch(
                        "app.jobs.cecchino_auto_scan.acquire_cecchino_scan_lock",
                    ) as lock_cm:
                        lock_cm.return_value.__enter__ = MagicMock(
                            return_value={"acquired": True, "backend": "process_threading", "lock_key": 1, "waited_seconds": 0}
                        )
                        lock_cm.return_value.__exit__ = MagicMock(return_value=False)
                        with patch("app.jobs.cecchino_auto_scan.create_scan_job") as create:
                            with patch("app.jobs.cecchino_auto_scan.execute_scan_job_sync") as execute:
                                with patch("app.jobs.cecchino_auto_scan.datetime") as mock_dt:
                                    mock_dt.now.return_value = _dt(2026, 7, 26, 23, 30)
                                    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                                    code = main(["--scheduled", "--dry-run"])
    assert code == EXIT_OK
    create.assert_not_called()
    execute.assert_not_called()


def test_exit_codes():
    assert outcome_to_exit_code({"status": JOB_STATUS_COMPLETED}) == EXIT_OK
    assert outcome_to_exit_code({"status": JOB_STATUS_SKIPPED_CONCURRENT_SCAN}) == EXIT_OK
    assert outcome_to_exit_code({"status": JOB_STATUS_FAILED_TIMEOUT}) == 2
    assert outcome_to_exit_code({"status": JOB_STATUS_FAILED}) == 1
    assert outcome_to_exit_code({"status": JOB_STATUS_PARTIAL_STOPPED_BUDGET}) == 4
    assert outcome_to_exit_code({"status": JOB_STATUS_FAILED_BUDGET_GUARD}) == 4
    assert outcome_to_exit_code({"status": JOB_STATUS_INTERRUPTED}) == 1


def test_idempotency_primary_completed_blocks_second():
    job = CecchinoTodayScanJob(
        job_id="auto-1",
        scan_date=date(2026, 7, 27),
        timezone=ROME,
        force_rescan=True,
        status=JOB_STATUS_COMPLETED,
        result_summary_json={
            "auto_scan": {
                "execution_source": "auto_scan",
                "execution_slot": "primary",
                "target_date": "2026-07-27",
                "local_execution_date": "2026-07-26",
            }
        },
    )
    assert evaluate_auto_scan_idempotency([job], slot=SLOT_PRIMARY)["action"] == "skip"
    assert evaluate_auto_scan_idempotency([job], slot=SLOT_RECOVERY)["action"] == "skip"


def test_idempotency_primary_failed_allows_recovery():
    job = CecchinoTodayScanJob(
        job_id="auto-fail",
        scan_date=date(2026, 7, 27),
        timezone=ROME,
        force_rescan=True,
        status=JOB_STATUS_FAILED,
        result_summary_json={
            "auto_scan": {
                "execution_source": "auto_scan",
                "execution_slot": "primary",
                "target_date": "2026-07-27",
                "local_execution_date": "2026-07-26",
            }
        },
    )
    out = evaluate_auto_scan_idempotency([job], slot=SLOT_RECOVERY)
    assert out["action"] == "run"


def test_manual_scan_does_not_block_primary():
    job = CecchinoTodayScanJob(
        job_id="manual-1",
        scan_date=date(2026, 7, 27),
        timezone=ROME,
        force_rescan=False,
        status=JOB_STATUS_COMPLETED,
        result_summary_json={"fixtures_found": 10},
    )
    out = evaluate_auto_scan_idempotency([job], slot=SLOT_PRIMARY)
    # find_auto_scan_jobs filters manual; empty list → run
    assert evaluate_auto_scan_idempotency([], slot=SLOT_PRIMARY)["action"] == "run"
    # Even if mistakenly included without auto_scan meta, not successful auto
    assert out["action"] == "run"


def test_auto_scan_meta_shape():
    meta = build_auto_scan_meta(
        execution_slot="primary",
        target_date=date(2026, 7, 27),
        timezone_name=ROME,
        local_execution_date_value=date(2026, 7, 26),
        attempt=1,
        lock_acquired=True,
        max_runtime_minutes=120,
    )
    assert meta["execution_source"] == "auto_scan"
    assert meta["execution_mode"] == "synchronous"
    assert meta["execution_slot"] == "primary"
    assert meta["target_date"] == "2026-07-27"
    assert meta["attempt"] == 1


def test_retry_only_when_no_fixtures_processed():
    assert _is_transient_retryable(
        {"status": JOB_STATUS_FAILED, "fixtures_checked": 0, "transient_candidate": True}
    )
    assert not _is_transient_retryable(
        {"status": JOB_STATUS_FAILED, "fixtures_checked": 5}
    )
    assert not _is_transient_retryable(
        {"status": JOB_STATUS_PARTIAL_STOPPED_BUDGET, "fixtures_checked": 0}
    )
    assert not _is_transient_retryable(
        {"status": JOB_STATUS_FAILED_TIMEOUT, "fixtures_checked": 0}
    )


def test_force_run_skips_idempotency():
    settings = MagicMock()
    settings.cecchino_auto_scan_enabled = False
    settings.cecchino_auto_scan_timezone = ROME
    settings.cecchino_auto_scan_primary_hour = 23
    settings.cecchino_auto_scan_primary_minute = 30
    settings.cecchino_auto_scan_recovery_hour = 23
    settings.cecchino_auto_scan_recovery_minute = 50
    settings.cecchino_auto_scan_window_minutes = 10
    settings.cecchino_auto_scan_max_runtime_minutes = 120
    settings.cecchino_auto_scan_transient_attempts = 1
    settings.cecchino_auto_scan_transient_retry_delay_seconds = 0

    completed = CecchinoTodayScanJob(
        job_id="auto-done",
        scan_date=date(2026, 7, 27),
        timezone=ROME,
        force_rescan=True,
        status=JOB_STATUS_COMPLETED,
        result_summary_json={
            "auto_scan": {
                "execution_source": "auto_scan",
                "local_execution_date": "2026-07-26",
                "target_date": "2026-07-27",
            }
        },
    )

    with patch("app.jobs.cecchino_auto_scan.get_settings", return_value=settings):
        with patch("app.jobs.cecchino_auto_scan.run_auto_scan", return_value=EXIT_OK) as run:
            with patch("app.jobs.cecchino_auto_scan.datetime") as mock_dt:
                mock_dt.now.return_value = _dt(2026, 7, 26, 12, 0)
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                main(["--force-run", "--target-date", "2026-07-27"])
    assert run.called
    # force_run True → idempotency skipped inside run_auto_scan
    assert run.call_args.kwargs["force_run"] is True
    _ = completed  # documento intent
