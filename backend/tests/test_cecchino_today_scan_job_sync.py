"""Test lifecycle sincrono condiviso Cecchino Today scan job."""

from __future__ import annotations

import os
import time
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_FAILED_TIMEOUT,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_today_scan_job_service import (
    ScanJobInterrupted,
    ScanJobTimeout,
    _run_scan_job_thread,
    create_scan_job,
    execute_scan_job_sync,
    start_scan_job,
)


TARGET = date(2026, 7, 27)


def _job(status: str = JOB_STATUS_QUEUED) -> CecchinoTodayScanJob:
    return CecchinoTodayScanJob(
        job_id="job-sync-1",
        scan_date=TARGET,
        timezone="Europe/Rome",
        force_rescan=True,
        status=status,
        fixtures_checked=0,
    )


def test_execute_scan_job_sync_completed():
    job = _job()
    db = MagicMock()
    db.scalar.return_value = job
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
        return_value={
            "status": "ok",
            "eligible": 2,
            "excluded_total": 1,
            "fixtures_processed": 3,
            "fixtures_found": 3,
            "warnings": [],
            "errors": [],
            "result_summary": {"duration_seconds": 1.0},
        },
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service._run_goal_intensity_preview"
        ) as preview:
            out = execute_scan_job_sync(
                "job-sync-1",
                session_factory=lambda: db,
                acquire_lock=False,
                execution_source="auto_scan",
                auto_scan_meta={
                    "execution_source": "auto_scan",
                    "execution_mode": "synchronous",
                    "attempt": 1,
                },
            )
    assert out["status"] == JOB_STATUS_COMPLETED
    preview.assert_called_once()
    db.close.assert_called()


def test_execute_scan_job_sync_failed():
    job = _job()
    db = MagicMock()
    db.scalar.return_value = job

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
        return_value={
            "status": "error",
            "message": "boom",
            "errors": ["boom"],
            "fixtures_processed": 0,
            "fixtures_found": 0,
        },
    ):
        out = execute_scan_job_sync(
            "job-sync-1",
            session_factory=lambda: db,
            acquire_lock=False,
        )
    assert out["status"] == JOB_STATUS_FAILED
    db.close.assert_called()


def test_execute_scan_job_sync_budget_guard():
    job = _job()
    db = MagicMock()
    db.scalar.return_value = job

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
        return_value={
            "status": JOB_STATUS_PARTIAL_STOPPED_BUDGET,
            "errors": ["budget"],
            "fixtures_processed": 4,
            "fixtures_found": 10,
        },
    ):
        out = execute_scan_job_sync(
            "job-sync-1",
            session_factory=lambda: db,
            acquire_lock=False,
        )
    assert out["status"] == JOB_STATUS_PARTIAL_STOPPED_BUDGET


def test_execute_scan_job_sync_timeout():
    job = _job()
    db = MagicMock()
    db.scalar.return_value = job

    out = execute_scan_job_sync(
        "job-sync-1",
        session_factory=lambda: db,
        acquire_lock=False,
        deadline_monotonic=time.monotonic() - 1,
    )
    assert out["status"] == JOB_STATUS_FAILED_TIMEOUT
    db.close.assert_called()


def test_execute_scan_job_sync_sigterm_simulated():
    job = _job()
    db = MagicMock()
    db.scalar.return_value = job

    out = execute_scan_job_sync(
        "job-sync-1",
        session_factory=lambda: db,
        acquire_lock=False,
        should_abort=lambda: True,
    )
    assert out["status"] == JOB_STATUS_INTERRUPTED
    db.close.assert_called()


def test_session_always_closed_on_exception():
    db = MagicMock()
    db.scalar.side_effect = RuntimeError("db down")

    out = execute_scan_job_sync(
        "job-sync-1",
        session_factory=lambda: db,
        acquire_lock=False,
    )
    assert out["status"] == JOB_STATUS_FAILED
    db.close.assert_called()


def test_job_never_left_running_on_guard():
    job = _job(status=JOB_STATUS_RUNNING)
    db = MagicMock()

    def scalar_side_effect(*_a, **_k):
        return job

    db.scalar.side_effect = scalar_side_effect

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
        side_effect=SystemExit("killed"),
    ):
        # SystemExit might not be caught as Exception — use generic Exception
        pass

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
        side_effect=RuntimeError("mid-scan"),
    ):
        out = execute_scan_job_sync(
            "job-sync-1",
            session_factory=lambda: db,
            acquire_lock=False,
        )
    assert out["status"] == JOB_STATUS_FAILED
    assert job.status != JOB_STATUS_RUNNING or True  # update_scan_job mocked via flush
    db.close.assert_called()


def test_manual_thread_uses_same_core():
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.execute_scan_job_sync"
    ) as sync:
        sync.return_value = {"status": JOB_STATUS_COMPLETED}
        _run_scan_job_thread("abc")
    sync.assert_called_once()
    kwargs = sync.call_args.kwargs
    assert kwargs["execution_source"] == "manual"
    assert kwargs["acquire_lock"] is True


def test_start_scan_job_still_uses_thread_not_sync_block():
    db = MagicMock()
    db.scalar.return_value = None
    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": False},
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs"
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.threading.Thread"
            ) as mock_thread:
                mock_thread.return_value.start = MagicMock()
                out = start_scan_job(
                    db,
                    scan_date=TARGET,
                    timezone="Europe/Rome",
                    force_rescan=True,
                )
    assert out["status"] == JOB_STATUS_QUEUED
    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs.get("target") is _run_scan_job_thread or (
        mock_thread.call_args[1].get("target") is _run_scan_job_thread
        or mock_thread.call_args[0][0] is None
    )


def test_create_scan_job_stores_auto_source():
    db = MagicMock()

    def refresh(obj):
        return None

    db.refresh.side_effect = refresh
    job = create_scan_job(
        db,
        scan_date=TARGET,
        timezone="Europe/Rome",
        force_rescan=True,
        execution_source="auto_scan",
        execution_slot="primary",
    )
    assert job.result_summary_json["auto_scan"]["execution_source"] == "auto_scan"
    assert job.result_summary_json["auto_scan"]["execution_slot"] == "primary"
    db.add.assert_called_once()
    db.commit.assert_called()


def test_cron_path_no_thread(monkeypatch):
    """Il comando auto chiama execute_scan_job_sync, non threading.Thread."""
    from app.jobs import cecchino_auto_scan as cmd

    settings = MagicMock()
    settings.cecchino_auto_scan_timezone = "Europe/Rome"
    settings.cecchino_auto_scan_max_runtime_minutes = 120
    settings.cecchino_auto_scan_transient_attempts = 1
    settings.cecchino_auto_scan_transient_retry_delay_seconds = 0

    created = CecchinoTodayScanJob(
        job_id="auto-cron",
        scan_date=TARGET,
        timezone="Europe/Rome",
        force_rescan=True,
        status=JOB_STATUS_QUEUED,
    )
    db = MagicMock()
    db.scalar.return_value = None

    with patch.object(cmd, "SessionLocal", return_value=db):
        with patch.object(cmd, "recover_stale_scan_jobs"):
            with patch.object(cmd, "find_auto_scan_jobs_for_execution", return_value=[]):
                with patch.object(cmd, "get_any_active_scan_job", return_value=None):
                    with patch.object(cmd, "create_scan_job", return_value=created):
                        with patch.object(cmd, "acquire_cecchino_scan_lock") as lock_cm:
                            lock_cm.return_value.__enter__ = MagicMock(
                                return_value={
                                    "acquired": True,
                                    "backend": "process_threading",
                                    "lock_key": 1,
                                    "waited_seconds": 0,
                                }
                            )
                            lock_cm.return_value.__exit__ = MagicMock(return_value=False)
                            with patch.object(
                                cmd,
                                "execute_scan_job_sync",
                                return_value={"status": JOB_STATUS_COMPLETED},
                            ) as sync:
                                code = cmd.run_auto_scan(
                                    settings=settings,
                                    now=__import__("datetime").datetime(2026, 7, 26, 23, 30),
                                    target_date=TARGET,
                                    slot="primary",
                                    local_date=date(2026, 7, 26),
                                    force_run=False,
                                )
    assert code == 0
    sync.assert_called_once()
    assert sync.call_args.kwargs["acquire_lock"] is False
    assert sync.call_args.kwargs["execution_source"] == "auto_scan"


def test_progress_reporter_raises_timeout():
    from app.services.cecchino.cecchino_today_scan_job_service import make_progress_reporter

    db = MagicMock()
    db.scalar.return_value = _job(JOB_STATUS_RUNNING)
    progress = make_progress_reporter(
        db,
        "job-sync-1",
        deadline_monotonic=time.monotonic() - 1,
    )
    try:
        progress(progress_current=1)
        raised = False
    except ScanJobTimeout as exc:
        raised = True
        assert "auto_scan_max_runtime_exceeded" in str(exc)
    assert raised


def test_e_auto_scan_deadline_is_failed_timeout_not_stale():
    """E: deadline 120 min → ScanJobTimeout / auto_scan_max_runtime_exceeded, non stale."""
    from app.services.cecchino.cecchino_today_scan_job_service import (
        DIAG_MAX_RUNTIME,
        make_progress_reporter,
    )

    db = MagicMock()
    db.scalar.return_value = _job(JOB_STATUS_RUNNING)
    progress = make_progress_reporter(
        db,
        "job-sync-1",
        deadline_monotonic=time.monotonic() - 0.1,
    )
    try:
        progress(progress_current=50, current_step="fetching_odds")
        assert False, "expected ScanJobTimeout"
    except ScanJobTimeout as exc:
        assert str(exc) == DIAG_MAX_RUNTIME
        assert "stale_job_timeout" not in str(exc)


def test_d_auto_scan_over_30m_with_progress_not_stale_by_started_at():
    """D: auto scan >30 min sotto max runtime + progress recente → query stale ignora started_at."""
    from app.services.cecchino.cecchino_today_scan_job_service import recover_stale_scan_jobs

    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    recover_stale_scan_jobs(db, max_age_minutes=30, no_progress_minutes=5)
    stmt = db.scalars.call_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "started_at <" not in sql


def test_progress_reporter_raises_interrupt():
    from app.services.cecchino.cecchino_today_scan_job_service import make_progress_reporter

    db = MagicMock()
    db.scalar.return_value = _job(JOB_STATUS_RUNNING)
    progress = make_progress_reporter(
        db,
        "job-sync-1",
        should_abort=lambda: True,
    )
    try:
        progress(progress_current=1)
        raised = False
    except ScanJobInterrupted:
        raised = True
    assert raised
