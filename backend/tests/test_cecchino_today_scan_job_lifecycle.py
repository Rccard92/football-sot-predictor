"""Test lifecycle job scan Cecchino Today (Fase 17)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_today_scan_job_service import (
    _run_scan_job_thread,
    get_latest_scan_job,
    get_latest_jobs_by_dates,
    recover_stale_scan_jobs,
    start_scan_job,
    update_scan_job,
)

TARGET_DATE = date(2026, 6, 5)


def test_start_scan_job_uses_requested_date_not_today():
    db = MagicMock()
    db.scalar.return_value = None
    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": False},
    ):
        with patch("app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs"):
            with patch("app.services.cecchino.cecchino_today_scan_job_service.threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                out = start_scan_job(
                    db,
                    scan_date=TARGET_DATE,
                    timezone="Europe/Rome",
                )
    assert out["scan_date"] == "2026-06-05"
    added = db.add.call_args[0][0]
    assert added.scan_date == TARGET_DATE


def test_recover_stale_queued_job_by_created_at():
    db = MagicMock()
    stale = CecchinoTodayScanJob(
        job_id="queued-stale",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_QUEUED,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=45),
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    db.scalars.return_value.all.return_value = [stale]
    count = recover_stale_scan_jobs(db, max_age_minutes=30)
    assert count == 1
    assert stale.status == JOB_STATUS_FAILED
    assert "stale_job_timeout" in (stale.errors_json or [])[0]


def test_recover_stale_running_job_by_updated_at():
    db = MagicMock()
    now = datetime.now(timezone.utc)
    stale = CecchinoTodayScanJob(
        job_id="running-stale",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        started_at=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=45),
    )
    db.scalars.return_value.all.return_value = [stale]
    count = recover_stale_scan_jobs(db, max_age_minutes=30)
    assert count == 1
    assert stale.status == JOB_STATUS_FAILED


def test_update_scan_job_sets_updated_at():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="jid",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
        return_value=job,
    ):
        update_scan_job(db, "jid", current_step="fetching_odds", progress_current=3)
    assert job.current_step == "fetching_odds"
    assert job.progress_current == 3
    assert job.updated_at is not None
    assert job.updated_at.year >= 2026


def test_run_scan_job_thread_marks_failed_on_exception():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="fail-job",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status=JOB_STATUS_QUEUED,
    )

    def get_job_side_effect(_db, job_id):
        return job

    with patch("app.services.cecchino.cecchino_today_scan_job_service.SessionLocal", return_value=db):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
            side_effect=get_job_side_effect,
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
                side_effect=RuntimeError("boom"),
            ):
                _run_scan_job_thread("fail-job")

    assert job.status == JOB_STATUS_FAILED
    assert job.finished_at is not None
    assert any("boom" in e for e in (job.errors_json or []))


def test_run_scan_job_thread_marks_completed_on_success():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="ok-job",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status=JOB_STATUS_QUEUED,
    )

    with patch("app.services.cecchino.cecchino_today_scan_job_service.SessionLocal", return_value=db):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
            return_value=job,
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
                return_value={
                    "status": "ok",
                    "eligible": 2,
                    "excluded_total": 1,
                    "fixtures_found": 10,
                    "fixtures_processed": 10,
                    "excluded_summary": {},
                    "result_summary": {"duration_seconds": 1.0},
                    "warnings": [],
                    "errors": [],
                },
            ):
                _run_scan_job_thread("ok-job")

    assert job.status == JOB_STATUS_COMPLETED
    assert job.finished_at is not None


def test_get_latest_scan_job_calls_recover():
    db = MagicMock()
    db.scalar.return_value = None
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs",
    ) as mock_recover:
        get_latest_scan_job(db, TARGET_DATE)
    mock_recover.assert_called_once_with(db)


def test_list_available_days_includes_scan_status():
    from app.services.cecchino.cecchino_today_service import list_available_days

    db = MagicMock()
    active = CecchinoTodayScanJob(
        job_id="active-id",
        scan_date=date(2026, 6, 4),
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
    )
    with patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=date(2026, 6, 4)):
        with patch("app.services.cecchino.cecchino_today_service.rome_tomorrow", return_value=date(2026, 6, 5)):
            with patch("app.services.cecchino.cecchino_today_service._aggregate_scan_dates", return_value={}):
                with patch(
                    "app.services.cecchino.cecchino_today_scan_job_service.recover_stale_scan_jobs",
                ):
                    with patch(
                        "app.services.cecchino.cecchino_today_scan_job_service.get_active_jobs_by_dates",
                        return_value={date(2026, 6, 4): active},
                    ):
                        with patch(
                            "app.services.cecchino.cecchino_today_scan_job_service.get_latest_jobs_by_dates",
                            return_value={date(2026, 6, 4): active},
                        ):
                            payload = list_available_days(db, timezone="Europe/Rome", window_days=0)
    today_entry = next(d for d in payload["days"] if d["date"] == "2026-06-04")
    assert today_entry["scan_status"] == "running"
    assert today_entry["active_job_id"] == "active-id"


def test_get_latest_jobs_by_dates_picks_most_recent():
    db = MagicMock()
    older = CecchinoTodayScanJob(
        job_id="old",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_FAILED,
        created_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
    )
    newer = CecchinoTodayScanJob(
        job_id="new",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_COMPLETED,
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )
    db.scalars.return_value.all.return_value = [newer, older]
    out = get_latest_jobs_by_dates(db, [TARGET_DATE])
    assert out[TARGET_DATE].job_id == "new"
