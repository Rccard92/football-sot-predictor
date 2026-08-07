"""Freshness / source_revision Bet Builder — SHA-256 stabile, nessuna cache."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.cecchino_today_scan_job import (
    JOB_ACTIVE_STATUSES,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_bet_builder_constants import (
    FRESHNESS_WARNING_SCAN_IN_PROGRESS,
)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def build_source_generated_from(
    *,
    scan_date: date,
    fixtures: list[CecchinoTodayFixture],
    latest_job: CecchinoTodayScanJob | None,
    max_v31_generated_at: str | None,
    max_gi_snapshot_at: str | None,
) -> dict[str, Any]:
    max_fixture_updated = None
    for row in fixtures:
        ts = getattr(row, "updated_at", None)
        if ts is None:
            continue
        iso = _iso(ts)
        if iso is not None and (max_fixture_updated is None or iso > max_fixture_updated):
            max_fixture_updated = iso

    job_meta: dict[str, Any] | None = None
    if latest_job is not None:
        job_meta = {
            "job_id": latest_job.job_id,
            "status": latest_job.status,
            "finished_at": _iso(latest_job.finished_at),
            "updated_at": _iso(latest_job.updated_at),
            "started_at": _iso(latest_job.started_at),
        }

    return {
        "scan_date": scan_date.isoformat(),
        "fixture_count": len(fixtures),
        "max_fixture_updated_at": max_fixture_updated,
        "max_purchasability_v31_generated_at": max_v31_generated_at,
        "max_goal_intensity_snapshot_at": max_gi_snapshot_at,
        "latest_scan_job": job_meta,
    }


def compute_source_revision(source_generated_from: dict[str, Any]) -> str:
    digest = hashlib.sha256(_stable_json(source_generated_from).encode("utf-8")).hexdigest()
    return digest


def _get_latest_scan_job_readonly(db: Session, scan_date: date) -> CecchinoTodayScanJob | None:
    """Latest job senza recover_stale (read-only Bet Builder)."""
    return db.scalar(
        select(CecchinoTodayScanJob)
        .where(CecchinoTodayScanJob.scan_date == scan_date)
        .order_by(desc(CecchinoTodayScanJob.created_at))
        .limit(1),
    )


def resolve_source_scan_status(
    db: Session,
    scan_date: date,
) -> tuple[str | None, CecchinoTodayScanJob | None, str | None]:
    """Ritorna (source_scan_status, latest_job, freshness_warning).

    Se non esiste job affidabile, status=None (non inventato).
    Nessuna write / nessun recover stale.
    """
    latest = _get_latest_scan_job_readonly(db, scan_date)
    if latest is None:
        return None, None, None
    status = str(latest.status or "").strip() or None
    warning = None
    if status in JOB_ACTIVE_STATUSES:
        warning = FRESHNESS_WARNING_SCAN_IN_PROGRESS
    return status, latest, warning
