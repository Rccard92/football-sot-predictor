"""Test progress_pct e finalizzazione job Cecchino Today (Fase 18)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_today_scan_job_service import (
    _compute_progress_pct,
    _run_scan_job_thread,
    job_to_dict,
    make_progress_reporter,
    recover_stale_scan_jobs,
    update_scan_job,
)

TARGET_DATE = date(2026, 6, 5)


def test_compute_progress_pct_examples():
    assert float(_compute_progress_pct(208, 433)) == 48.0
    assert float(_compute_progress_pct(432, 433)) == 99.8
    assert float(_compute_progress_pct(0, 433)) == 0.0
    assert _compute_progress_pct(0, 0) is None


def test_progress_reporter_step_only_does_not_wipe_pct():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="jid",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=208,
        progress_total=433,
        progress_pct=Decimal("48.0"),
    )

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
        return_value=job,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.update_scan_job",
            side_effect=lambda _db, _jid, **kwargs: None,
        ) as mock_update:
            reporter = make_progress_reporter(db, "jid")
            reporter(current_step="fetching_odds")

    assert job.progress_pct == Decimal("48.0")
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs.get("progress_pct") == 48.0
    assert call_kwargs.get("current_step") == "fetching_odds"


def test_progress_reporter_updates_pct_from_current_total():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="jid",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=0,
        progress_total=433,
        progress_pct=None,
    )

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
        return_value=job,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.update_scan_job",
        ) as mock_update:
            reporter = make_progress_reporter(db, "jid")
            reporter(progress_current=432, progress_total=433)

    assert mock_update.call_args.kwargs["progress_pct"] == 99.8


def test_job_to_dict_resolves_pct_from_current_total():
    job = CecchinoTodayScanJob(
        job_id="jid",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=208,
        progress_total=433,
        progress_pct=None,
    )
    d = job_to_dict(job)
    assert d["progress_pct"] == 48.0


def test_recover_stale_running_no_progress_6_minutes():
    db = MagicMock()
    now = datetime.now(timezone.utc)
    stale = CecchinoTodayScanJob(
        job_id="stale-np",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        started_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=6),
    )
    db.scalars.return_value.all.return_value = [stale]
    count = recover_stale_scan_jobs(db, max_age_minutes=30, no_progress_minutes=5)
    assert count == 1
    assert stale.status == JOB_STATUS_FAILED


def test_run_scan_job_thread_completed_sets_progress_100():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="ok-job",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status=JOB_STATUS_RUNNING,
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
                    "eligible": 3,
                    "excluded_total": 10,
                    "fixtures_found": 433,
                    "fixtures_processed": 433,
                    "total_discovered": 433,
                    "excluded_summary": {},
                    "result_summary": {"duration_seconds": 120.0},
                    "warnings": [],
                    "errors": ["fixture 999: boom"],
                },
            ):
                _run_scan_job_thread("ok-job")

    assert job.status == JOB_STATUS_COMPLETED
    assert job.progress_pct == Decimal("100.0")
    assert job.progress_current == 433
    assert job.progress_total == 433
    assert job.finished_at is not None


def test_update_scan_job_sets_updated_at_on_progress():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="jid",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=False,
        status=JOB_STATUS_RUNNING,
        progress_current=1,
        progress_total=10,
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
        return_value=job,
    ):
        update_scan_job(db, "jid", progress_current=2, progress_pct=20.0, current_step="fetching_odds")
    assert job.progress_current == 2
    assert job.current_step == "fetching_odds"
    assert job.updated_at.year >= 2026
