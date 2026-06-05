"""Job asincrono scan giornaliera Cecchino Today."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_today_scan_job import (
    JOB_ACTIVE_STATUSES,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics
from app.services.cecchino.cecchino_today_service import run_scan_day

logger = logging.getLogger(__name__)

STALE_JOB_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def job_to_dict(job: CecchinoTodayScanJob) -> dict[str, Any]:
    progress_pct = float(job.progress_pct) if job.progress_pct is not None else None
    return {
        "job_id": job.job_id,
        "scan_date": job.scan_date.isoformat(),
        "timezone": job.timezone,
        "force_rescan": bool(job.force_rescan),
        "status": job.status,
        "current_step": job.current_step,
        "progress_current": int(job.progress_current or 0),
        "progress_total": job.progress_total,
        "progress_pct": progress_pct,
        "fixtures_found": int(job.fixtures_found or 0),
        "fixtures_checked": int(job.fixtures_checked or 0),
        "odds_checked": int(job.odds_checked or 0),
        "eligible_count": int(job.eligible_count or 0),
        "excluded_count": int(job.excluded_count or 0),
        "excluded_summary": job.excluded_summary_json or {},
        "result_summary": job.result_summary_json,
        "warnings": list(job.warnings_json or []),
        "errors": list(job.errors_json or []),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def recover_stale_scan_jobs(db: Session, *, max_age_minutes: int = STALE_JOB_MINUTES) -> int:
    cutoff = _utcnow() - timedelta(minutes=max_age_minutes)
    rows = list(
        db.scalars(
            select(CecchinoTodayScanJob).where(
                CecchinoTodayScanJob.status.in_(tuple(JOB_ACTIVE_STATUSES)),
                or_(
                    and_(
                        CecchinoTodayScanJob.status == JOB_STATUS_QUEUED,
                        CecchinoTodayScanJob.created_at < cutoff,
                    ),
                    and_(
                        CecchinoTodayScanJob.status == JOB_STATUS_RUNNING,
                        or_(
                            and_(
                                CecchinoTodayScanJob.started_at.isnot(None),
                                CecchinoTodayScanJob.started_at < cutoff,
                            ),
                            CecchinoTodayScanJob.updated_at < cutoff,
                        ),
                    ),
                ),
            ),
        ).all(),
    )
    count = 0
    for row in rows:
        row.status = JOB_STATUS_FAILED
        row.finished_at = _utcnow()
        row.current_step = "completed"
        row.updated_at = _utcnow()
        errs = list(row.errors_json or [])
        errs.append("stale_job_timeout")
        row.errors_json = errs
        count += 1
    if count:
        db.commit()
    return count


def get_running_job_for_date(db: Session, scan_date: date) -> CecchinoTodayScanJob | None:
    return db.scalar(
        select(CecchinoTodayScanJob)
        .where(
            CecchinoTodayScanJob.scan_date == scan_date,
            CecchinoTodayScanJob.status.in_(tuple(JOB_ACTIVE_STATUSES)),
        )
        .order_by(desc(CecchinoTodayScanJob.created_at))
        .limit(1),
    )


def get_latest_scan_job(db: Session, scan_date: date) -> CecchinoTodayScanJob | None:
    recover_stale_scan_jobs(db)
    return db.scalar(
        select(CecchinoTodayScanJob)
        .where(CecchinoTodayScanJob.scan_date == scan_date)
        .order_by(desc(CecchinoTodayScanJob.created_at))
        .limit(1),
    )


def get_scan_job(db: Session, job_id: str) -> CecchinoTodayScanJob | None:
    return db.scalar(select(CecchinoTodayScanJob).where(CecchinoTodayScanJob.job_id == job_id))


def _update_job_fields(job: CecchinoTodayScanJob, **kwargs: Any) -> None:
    for key, val in kwargs.items():
        if not hasattr(job, key):
            continue
        if key == "progress_pct" and val is not None:
            job.progress_pct = Decimal(str(round(float(val), 1)))
        else:
            setattr(job, key, val)


def update_scan_job(db: Session, job_id: str, **kwargs: Any) -> CecchinoTodayScanJob | None:
    job = get_scan_job(db, job_id)
    if job is None:
        return None
    _update_job_fields(job, **kwargs)
    job.updated_at = _utcnow()
    db.flush()
    return job


def make_progress_reporter(db: Session, job_id: str) -> Callable[..., None]:
    def progress(**kwargs: Any) -> None:
        current = kwargs.get("progress_current")
        total = kwargs.get("progress_total")
        pct = None
        if current is not None and total:
            pct = round(float(current) / float(total) * 100.0, 1)
        elif kwargs.get("progress_pct") is not None:
            pct = kwargs.get("progress_pct")
        update_scan_job(
            db,
            job_id,
            progress_pct=pct,
            **{k: v for k, v in kwargs.items() if k != "progress_pct"},
        )
        db.commit()

    return progress


def _run_scan_job_thread(job_id: str) -> None:
    db = SessionLocal()
    terminal = False
    try:
        job = get_scan_job(db, job_id)
        if job is None:
            logger.warning("Cecchino scan job not found job_id=%s", job_id)
            return
        logger.info(
            "Cecchino scan job starting job_id=%s scan_date=%s",
            job_id,
            job.scan_date.isoformat(),
        )
        update_scan_job(
            db,
            job_id,
            status=JOB_STATUS_RUNNING,
            started_at=_utcnow(),
            current_step="fetching_fixtures",
        )
        db.commit()

        metrics = ScanRunMetrics(started_at=time.time())
        progress = make_progress_reporter(db, job_id)
        report = run_scan_day(
            db,
            scan_date=job.scan_date,
            timezone=job.timezone,
            force_rescan=bool(job.force_rescan),
            job_id=job_id,
            progress=progress,
            metrics=metrics,
        )

        status = report.get("status")
        if status == "already_scanned":
            update_scan_job(
                db,
                job_id,
                status=JOB_STATUS_COMPLETED,
                finished_at=_utcnow(),
                current_step="completed",
                result_summary_json={
                    "status": "already_scanned",
                    "scan_meta": report.get("scan_meta"),
                },
                warnings_json=[],
            )
            db.commit()
            terminal = True
            return

        if status != "ok":
            update_scan_job(
                db,
                job_id,
                status=JOB_STATUS_FAILED,
                finished_at=_utcnow(),
                current_step="completed",
                errors_json=list(report.get("errors") or [report.get("message", "scan failed")]),
                warnings_json=list(report.get("warnings") or []),
                result_summary_json=report.get("result_summary"),
            )
            db.commit()
            terminal = True
            return

        update_scan_job(
            db,
            job_id,
            status=JOB_STATUS_COMPLETED,
            finished_at=_utcnow(),
            current_step="completed",
            progress_pct=Decimal("100.0"),
            eligible_count=int(report.get("eligible") or 0),
            excluded_count=int(report.get("excluded_total") or 0),
            excluded_summary_json=dict(report.get("excluded_summary") or {}),
            result_summary_json=report.get("result_summary"),
            warnings_json=list(report.get("warnings") or []),
            errors_json=list(report.get("errors") or []),
            fixtures_found=int(report.get("fixtures_found") or report.get("total_discovered") or 0),
            fixtures_checked=int(report.get("fixtures_processed") or 0),
        )
        db.commit()
        terminal = True
        logger.info("Cecchino scan job completed job_id=%s scan_date=%s", job_id, job.scan_date.isoformat())
    except Exception as exc:
        logger.exception(
            "Cecchino Today scan job failed job_id=%s scan_date=%s step=runner",
            job_id,
            getattr(locals().get("job"), "scan_date", "?"),
        )
        try:
            db.rollback()
            job = get_scan_job(db, job_id)
            if job is not None:
                errs = list(job.errors_json or [])
                errs.append(str(exc)[:500])
                update_scan_job(
                    db,
                    job_id,
                    status=JOB_STATUS_FAILED,
                    finished_at=_utcnow(),
                    current_step="completed",
                    errors_json=errs,
                )
                db.commit()
                terminal = True
        except Exception:
            logger.exception("Failed to mark scan job as failed job_id=%s", job_id)
    finally:
        if not terminal:
            try:
                db.rollback()
                job = get_scan_job(db, job_id)
                if job is not None and job.status in JOB_ACTIVE_STATUSES:
                    errs = list(job.errors_json or [])
                    errs.append("job thread exited without terminal status")
                    update_scan_job(
                        db,
                        job_id,
                        status=JOB_STATUS_FAILED,
                        finished_at=_utcnow(),
                        current_step="completed",
                        errors_json=errs,
                    )
                    db.commit()
            except Exception:
                logger.exception("Failed guard cleanup for scan job job_id=%s", job_id)
        db.close()


def start_scan_job(
    db: Session,
    *,
    scan_date: date,
    timezone: str,
    force_rescan: bool = False,
) -> dict[str, Any]:
    from app.services.cecchino.cecchino_today_service import get_day_scan_meta

    recover_stale_scan_jobs(db)

    existing = get_running_job_for_date(db, scan_date)
    if existing is not None:
        if force_rescan:
            return {
                "status": "conflict",
                "message": "Scansione già in corso",
                "job_id": existing.job_id,
                "scan_date": scan_date.isoformat(),
            }
        return {
            "job_id": existing.job_id,
            "status": existing.status,
            "scan_date": scan_date.isoformat(),
            "message": "Scansione già in corso — job esistente restituito",
        }

    meta = get_day_scan_meta(db, scan_date, timezone=timezone)
    if not force_rescan and meta.get("has_scan"):
        return {
            "status": "already_scanned",
            "scan_date": scan_date.isoformat(),
            "message": "Giornata già scansionata. Usa force_rescan=true per aggiornare.",
            "scan_meta": meta,
        }

    job_id = str(uuid.uuid4())
    job = CecchinoTodayScanJob(
        job_id=job_id,
        scan_date=scan_date,
        timezone=timezone,
        force_rescan=force_rescan,
        status=JOB_STATUS_QUEUED,
        current_step="fetching_fixtures",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    thread = threading.Thread(
        target=_run_scan_job_thread,
        args=(job_id,),
        daemon=True,
        name=f"cecchino-scan-{job_id[:8]}",
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": JOB_STATUS_QUEUED,
        "scan_date": scan_date.isoformat(),
        "message": "Scansione avviata",
    }


def get_latest_jobs_by_dates(db: Session, dates: list[date]) -> dict[date, CecchinoTodayScanJob]:
    if not dates:
        return {}
    rows = list(
        db.scalars(
            select(CecchinoTodayScanJob)
            .where(CecchinoTodayScanJob.scan_date.in_(dates))
            .order_by(CecchinoTodayScanJob.scan_date, desc(CecchinoTodayScanJob.created_at)),
        ).all(),
    )
    out: dict[date, CecchinoTodayScanJob] = {}
    for row in rows:
        if row.scan_date not in out:
            out[row.scan_date] = row
    return out


def get_active_jobs_by_dates(db: Session, dates: list[date]) -> dict[date, CecchinoTodayScanJob]:
    if not dates:
        return {}
    rows = list(
        db.scalars(
            select(CecchinoTodayScanJob)
            .where(
                CecchinoTodayScanJob.scan_date.in_(dates),
                CecchinoTodayScanJob.status.in_(tuple(JOB_ACTIVE_STATUSES)),
            )
            .order_by(desc(CecchinoTodayScanJob.created_at)),
        ).all(),
    )
    out: dict[date, CecchinoTodayScanJob] = {}
    for row in rows:
        if row.scan_date not in out:
            out[row.scan_date] = row
    return out
