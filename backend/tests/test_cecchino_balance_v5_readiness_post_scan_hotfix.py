"""Hotfix: Readiness post-scan isolation + timestamp server_default."""

from __future__ import annotations

import importlib.util
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_balance_v5_governance_decision import (
    CecchinoBalanceV5GovernanceDecision,
)
from app.models.cecchino_balance_v5_readiness_snapshot import (
    CecchinoBalanceV5ReadinessSnapshot,
)
from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    CecchinoTodayScanJob,
)
from app.models.mixins import TimestampMixin
from app.services.cecchino.cecchino_balance_v5_readiness import (
    BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING,
    safe_upsert_balance_readiness_daily_snapshot,
)
from app.services.cecchino.cecchino_today_scan_job_service import _run_scan_job_thread
from app.services.cecchino.cecchino_today_service import run_scan_day

TARGET_DATE = date(2026, 7, 21)


def _load_migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260721100000_balance_v5_readiness_timestamp_defaults.py"
    )
    spec = importlib.util.spec_from_file_location("mig_readiness_ts", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_revision_chain_and_defaults():
    mod = _load_migration_module()
    assert mod.revision == "20260721100000"
    assert mod.down_revision == "20260720180000"

    alter_calls: list[tuple] = []

    class _Bind:
        dialect = type("D", (), {"name": "postgresql"})()

    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = _Bind()

        def _capture_alter(table, column, **kwargs):
            alter_calls.append((table, column, kwargs.get("server_default")))

        mock_op.alter_column.side_effect = _capture_alter
        mod.upgrade()

    tables_cols = {(t, c) for t, c, _ in alter_calls}
    assert ("cecchino_balance_v5_readiness_snapshots", "created_at") in tables_cols
    assert ("cecchino_balance_v5_readiness_snapshots", "updated_at") in tables_cols
    assert ("cecchino_balance_v5_governance_decisions", "created_at") in tables_cols
    for _t, _c, default in alter_calls:
        assert default is not None
        assert "now()" in str(default)


def test_orm_timestamp_defaults_align_with_mixin():
    snap_created = CecchinoBalanceV5ReadinessSnapshot.__table__.c.created_at
    snap_updated = CecchinoBalanceV5ReadinessSnapshot.__table__.c.updated_at
    assert snap_created.server_default is not None
    assert snap_updated.server_default is not None
    assert issubclass(CecchinoBalanceV5ReadinessSnapshot, TimestampMixin)

    gov_created = CecchinoBalanceV5GovernanceDecision.__table__.c.created_at
    assert gov_created.server_default is not None
    assert gov_created.nullable is False


def test_snapshot_model_does_not_require_manual_created_at():
    cols = {c.key for c in CecchinoBalanceV5ReadinessSnapshot.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" in cols
    assert "created_at" in CecchinoBalanceV5ReadinessSnapshot.__mapper__.columns


def test_safe_upsert_rolls_back_accessory_session_on_integrity_error():
    snap_db = MagicMock()
    with patch("app.core.database.SessionLocal", return_value=snap_db):
        with patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.upsert_balance_readiness_daily_snapshot",
            side_effect=IntegrityError("INSERT", {}, Exception("created_at")),
        ):
            out = safe_upsert_balance_readiness_daily_snapshot(
                phase="after_today_scan",
                scan_date=TARGET_DATE,
                job_id="job-1",
            )
    assert out["status"] == "skipped"
    assert out["warning_code"] == BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING
    snap_db.rollback.assert_called()
    snap_db.close.assert_called()


def test_safe_upsert_success_path():
    snap_db = MagicMock()
    with patch("app.core.database.SessionLocal", return_value=snap_db):
        with patch(
            "app.services.cecchino.cecchino_balance_v5_readiness.upsert_balance_readiness_daily_snapshot",
            return_value={
                "status": "ok",
                "action": "created",
                "readiness_hash": "abc",
                "snapshot_date": TARGET_DATE.isoformat(),
            },
        ):
            out = safe_upsert_balance_readiness_daily_snapshot(
                phase="after_today_scan",
                scan_date=TARGET_DATE,
                job_id="job-ok",
            )
    assert out["status"] == "ok"
    assert out["action"] == "created"
    snap_db.rollback.assert_not_called()
    snap_db.close.assert_called()


def test_job_completed_when_readiness_fails_non_blocking():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="ready-fail",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status="queued",
    )
    report = {
        "status": "ok",
        "eligible": 14,
        "excluded_total": 161,
        "fixtures_found": 175,
        "fixtures_processed": 175,
        "excluded_summary": {},
        "result_summary": {
            "duration_seconds": 12.0,
            "api_calls_total": 40,
            "api_calls": {"fixtures": 1, "odds": 30, "teams": 9},
        },
        "warnings": [BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING],
        "errors": [],
        "scan_meta": {"has_scan": True},
    }
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.SessionLocal",
        return_value=db,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
            return_value=job,
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
                return_value=report,
            ):
                _run_scan_job_thread("ready-fail")

    assert job.status == JOB_STATUS_COMPLETED
    assert job.eligible_count == 14
    assert job.excluded_count == 161
    assert BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING in (job.warnings_json or [])
    assert BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING not in (job.errors_json or [])
    assert not any(
        "job thread exited without terminal status" in str(e)
        for e in (job.errors_json or [])
    )
    assert job.finished_at is not None


def test_job_completed_success_readiness_no_warning():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="ready-ok",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status="queued",
    )
    report = {
        "status": "ok",
        "eligible": 14,
        "excluded_total": 161,
        "fixtures_found": 175,
        "fixtures_processed": 175,
        "excluded_summary": {},
        "result_summary": {"duration_seconds": 10.0, "api_calls_total": 5},
        "warnings": [],
        "errors": [],
    }
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.SessionLocal",
        return_value=db,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
            return_value=job,
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
                return_value=report,
            ):
                _run_scan_job_thread("ready-ok")

    assert job.status == JOB_STATUS_COMPLETED
    assert job.warnings_json == []
    assert job.errors_json == []


def test_job_real_scan_failure_remains_failed():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="scan-boom",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status="queued",
    )
    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.SessionLocal",
        return_value=db,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
            return_value=job,
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
                side_effect=RuntimeError("scan pipeline boom"),
            ):
                _run_scan_job_thread("scan-boom")

    assert job.status == JOB_STATUS_FAILED
    assert any("scan pipeline boom" in e for e in (job.errors_json or []))


def test_run_scan_day_meta_survives_after_scan_report():
    db = MagicMock()
    report = {
        "status": "ok",
        "eligible": 2,
        "excluded_total": 1,
        "warnings": [],
        "errors": [],
    }
    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        side_effect=[
            {"has_scan": False},
            {"has_scan": True, "eligible_count": 2},
        ],
    ) as meta:
        with patch(
            "app.services.cecchino.cecchino_today_service.run_scan",
            return_value=report,
        ) as mock_scan:
            out = run_scan_day(
                db,
                scan_date=TARGET_DATE,
                timezone="Europe/Rome",
                force_rescan=True,
            )
    assert out["status"] == "ok"
    assert out["scan_meta"]["has_scan"] is True
    mock_scan.assert_called_once()
    assert meta.call_count == 2
