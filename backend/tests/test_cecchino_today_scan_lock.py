"""Test lock globale Cecchino Today scan."""

from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.services.cecchino.cecchino_today_scan_lock import (
    CECCHINO_TODAY_SCAN_LOCK_KEY,
    ScanLockNotAcquired,
    acquire_cecchino_scan_lock,
    _process_lock,
)


def test_process_fallback_acquire_and_release():
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    with acquire_cecchino_scan_lock(engine=engine) as payload:
        assert payload["acquired"] is True
        assert payload["backend"] == "process_threading"
        assert payload["lock_key"] == CECCHINO_TODAY_SCAN_LOCK_KEY
    # dopo exit il lock è rilasciato
    assert _process_lock.acquire(blocking=False)
    _process_lock.release()


def test_process_lock_not_acquired():
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    assert _process_lock.acquire(blocking=False)
    try:
        try:
            with acquire_cecchino_scan_lock(engine=engine):
                raise AssertionError("should not acquire")
        except ScanLockNotAcquired as exc:
            assert exc.payload["acquired"] is False
            assert exc.payload["backend"] == "process_threading"
    finally:
        _process_lock.release()


def test_two_concurrent_process_locks():
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    results: list[str] = []

    def worker(name: str) -> None:
        try:
            with acquire_cecchino_scan_lock(engine=engine):
                results.append(f"{name}:acquired")
                # tieni il lock un attimo
                threading.Event().wait(0.05)
                results.append(f"{name}:done")
        except ScanLockNotAcquired:
            results.append(f"{name}:skipped")

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    threading.Event().wait(0.01)
    t2.start()
    t1.join()
    t2.join()
    assert any(r.endswith(":acquired") for r in results)
    assert any(r.endswith(":skipped") for r in results) or results.count("a:done") + results.count(
        "b:done"
    ) >= 1


def test_postgresql_advisory_simulated():
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    conn = MagicMock()
    engine.connect.return_value.execution_options.return_value = conn
    conn.execute.return_value.scalar.side_effect = [True, True]  # try_lock, unlock

    with acquire_cecchino_scan_lock(engine=engine) as payload:
        assert payload["acquired"] is True
        assert payload["backend"] == "postgresql_advisory"
        assert payload["lock_key"] == CECCHINO_TODAY_SCAN_LOCK_KEY

    assert conn.close.called
    # try_lock + unlock
    assert conn.execute.call_count >= 2


def test_postgresql_lock_not_acquired_releases_connection():
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    conn = MagicMock()
    engine.connect.return_value.execution_options.return_value = conn
    conn.execute.return_value.scalar.return_value = False

    try:
        with acquire_cecchino_scan_lock(engine=engine):
            raise AssertionError("should not acquire")
    except ScanLockNotAcquired as exc:
        assert exc.payload["acquired"] is False
    assert conn.close.called


def test_execute_scan_job_sync_skips_api_when_lock_denied():
    from app.models.cecchino_today_scan_job import (
        JOB_STATUS_QUEUED,
        JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
        CecchinoTodayScanJob,
    )
    from app.services.cecchino.cecchino_today_scan_job_service import execute_scan_job_sync
    from app.services.cecchino.cecchino_today_scan_lock import ScanLockNotAcquired

    job = CecchinoTodayScanJob(
        job_id="j-lock",
        scan_date=__import__("datetime").date(2026, 7, 27),
        timezone="Europe/Rome",
        force_rescan=True,
        status=JOB_STATUS_QUEUED,
    )
    db = MagicMock()
    db.scalar.return_value = job

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.acquire_cecchino_scan_lock",
        side_effect=ScanLockNotAcquired(
            {"acquired": False, "backend": "process_threading", "lock_key": 1, "waited_seconds": 0}
        ),
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day"
        ) as run_scan:
            out = execute_scan_job_sync(
                "j-lock",
                session_factory=lambda: db,
                acquire_lock=True,
            )
    assert out["status"] == JOB_STATUS_SKIPPED_CONCURRENT_SCAN
    run_scan.assert_not_called()
    db.close.assert_called()


def test_manual_and_cron_share_same_lock_key():
    assert CECCHINO_TODAY_SCAN_LOCK_KEY == 0xCEC5C4A0
