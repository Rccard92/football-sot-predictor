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
    JOB_STATUS_FAILED_BUDGET_GUARD,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    CecchinoTodayScanJob,
)
from app.services.api_usage_context import BudgetGuardStop
from app.services.api_usage_service import check_api_budget_before_scan
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics
from app.services.cecchino.cecchino_today_service import run_scan_day

logger = logging.getLogger(__name__)

STALE_JOB_MINUTES = 30
STALE_NO_PROGRESS_MINUTES = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_progress_pct(current: int | None, total: int | None) -> Decimal | None:
    if current is None or not total or int(total) <= 0:
        return None
    return Decimal(str(round(float(current) / float(total) * 100.0, 1)))


def _resolve_job_progress_pct(job: CecchinoTodayScanJob) -> float | None:
    if job.progress_pct is not None:
        return float(job.progress_pct)
    pct = _compute_progress_pct(int(job.progress_current or 0), job.progress_total)
    return float(pct) if pct is not None else None


def job_to_dict(job: CecchinoTodayScanJob) -> dict[str, Any]:
    progress_pct = _resolve_job_progress_pct(job)
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


def recover_stale_scan_jobs(
    db: Session,
    *,
    max_age_minutes: int = STALE_JOB_MINUTES,
    no_progress_minutes: int = STALE_NO_PROGRESS_MINUTES,
) -> int:
    now = _utcnow()
    overall_cutoff = now - timedelta(minutes=max_age_minutes)
    no_progress_cutoff = now - timedelta(minutes=no_progress_minutes)
    rows = list(
        db.scalars(
            select(CecchinoTodayScanJob).where(
                CecchinoTodayScanJob.status.in_(tuple(JOB_ACTIVE_STATUSES)),
                or_(
                    and_(
                        CecchinoTodayScanJob.status == JOB_STATUS_QUEUED,
                        CecchinoTodayScanJob.created_at < overall_cutoff,
                    ),
                    and_(
                        CecchinoTodayScanJob.status == JOB_STATUS_RUNNING,
                        or_(
                            CecchinoTodayScanJob.updated_at < no_progress_cutoff,
                            and_(
                                CecchinoTodayScanJob.started_at.isnot(None),
                                CecchinoTodayScanJob.started_at < overall_cutoff,
                            ),
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
        if key == "progress_pct":
            if val is None:
                continue
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
        job = get_scan_job(db, job_id)
        if job is None:
            return

        fields = {k: v for k, v in kwargs.items() if k != "progress_pct"}
        current_raw = fields.get("progress_current", job.progress_current)
        total_raw = fields.get("progress_total", job.progress_total)
        current = int(current_raw) if current_raw is not None else None
        total = int(total_raw) if total_raw is not None else None

        pct: float | Decimal | None
        if kwargs.get("progress_pct") is not None:
            pct = kwargs.get("progress_pct")
        else:
            computed = _compute_progress_pct(current, total)
            pct = float(computed) if computed is not None else None
            if pct is None and job.progress_pct is not None:
                pct = float(job.progress_pct)

        update_fields: dict[str, Any] = dict(fields)
        if pct is not None:
            update_fields["progress_pct"] = pct

        update_scan_job(db, job_id, **update_fields)
        step = fields.get("current_step") or job.current_step
        logger.info(
            "CecchinoTodayJob job_id=%s progress=%s/%s pct=%s step=%s",
            job_id,
            current,
            total,
            pct,
            step,
        )
        db.commit()

    return progress


def _metrics_result_summary(
    metrics: ScanRunMetrics | None,
    *,
    report: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Propagazione contatori API/metriche senza alterare la logica di consumo."""
    if report and isinstance(report.get("result_summary"), dict):
        summary = dict(report["result_summary"])
        if metrics is not None:
            metrics.sync_api_calls_total()
            if not summary.get("api_calls_total") and metrics.api_calls_total:
                summary["api_calls"] = dict(metrics.api_calls)
                summary["api_calls_total"] = metrics.api_calls_total
                summary["api_calls_by_endpoint"] = dict(metrics.api_calls)
        return summary
    if metrics is None:
        return None
    duration = 0.0
    if metrics.started_at > 0:
        duration = max(0.0, time.time() - metrics.started_at)
    return metrics.to_result_summary(
        fixtures_found=int(metrics.fixtures_found or 0),
        after_competition_filter=int(metrics.after_competition_filter or 0),
        odds_checked=int(metrics.odds_checked or 0),
        eligible_count=0,
        excluded_count=0,
        excluded_summary=dict(metrics.excluded_summary or {}),
        duration_seconds=duration,
    )


def _run_scan_job_thread(job_id: str) -> None:
    db = SessionLocal()
    terminal = False
    metrics: ScanRunMetrics | None = None
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
            already_summary: dict[str, Any] = {
                "status": "already_scanned",
                "scan_meta": report.get("scan_meta"),
            }
            metrics_summary = _metrics_result_summary(metrics)
            if metrics_summary:
                already_summary["api_calls"] = metrics_summary.get("api_calls", {})
                already_summary["api_calls_total"] = metrics_summary.get(
                    "api_calls_total", 0
                )
                already_summary["api_calls_by_endpoint"] = metrics_summary.get(
                    "api_calls_by_endpoint", {}
                )
            update_scan_job(
                db,
                job_id,
                status=JOB_STATUS_COMPLETED,
                finished_at=_utcnow(),
                current_step="completed",
                result_summary_json=already_summary,
                warnings_json=[],
            )
            db.commit()
            terminal = True
            return

        if status != "ok":
            job_status = JOB_STATUS_FAILED
            if status in (JOB_STATUS_PARTIAL_STOPPED_BUDGET, JOB_STATUS_FAILED_BUDGET_GUARD):
                job_status = status
            update_scan_job(
                db,
                job_id,
                status=job_status,
                finished_at=_utcnow(),
                current_step="completed",
                errors_json=list(report.get("errors") or [report.get("message", "scan failed")]),
                warnings_json=list(report.get("warnings") or []),
                result_summary_json=_metrics_result_summary(metrics, report=report),
                progress_current=int(report.get("fixtures_processed") or 0),
                progress_total=int(report.get("fixtures_found") or report.get("total_discovered") or 0),
                eligible_count=int(report.get("eligible") or 0),
                excluded_count=int(report.get("excluded_total") or 0),
                excluded_summary_json=dict(report.get("excluded_summary") or {}),
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
            progress_current=int(report.get("fixtures_processed") or report.get("total_discovered") or 0),
            progress_total=int(report.get("fixtures_found") or report.get("total_discovered") or 0),
            progress_pct=Decimal("100.0"),
            eligible_count=int(report.get("eligible") or 0),
            excluded_count=int(report.get("excluded_total") or 0),
            excluded_summary_json=dict(report.get("excluded_summary") or {}),
            result_summary_json=_metrics_result_summary(metrics, report=report),
            warnings_json=list(report.get("warnings") or []),
            errors_json=list(report.get("errors") or []),
            fixtures_found=int(report.get("fixtures_found") or report.get("total_discovered") or 0),
            fixtures_checked=int(report.get("fixtures_processed") or 0),
        )
        db.commit()
        terminal = True
        logger.info(
            "CecchinoTodayJob job_id=%s completed scan_date=%s eligible=%s excluded=%s duration=%s",
            job_id,
            job.scan_date.isoformat(),
            report.get("eligible"),
            report.get("excluded_total"),
            (report.get("result_summary") or {}).get("duration_seconds"),
        )
        # Preview Intensità Goal v5 — non bloccante, non altera eligibility/scan
        try:
            from app.models.cecchino_today_fixture import (
                ELIGIBILITY_ELIGIBLE,
                CecchinoTodayFixture,
            )
            from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
                safe_preview_after_today_scan,
            )

            eligible_ids = list(
                db.scalars(
                    select(CecchinoTodayFixture.id).where(
                        CecchinoTodayFixture.scan_date == job.scan_date,
                        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
                    )
                ).all()
            )
            preview_ok = 0
            preview_err = 0
            for tid in eligible_ids:
                try:
                    out = safe_preview_after_today_scan(db, int(tid))
                    if out.get("status") == "error":
                        preview_err += 1
                    else:
                        preview_ok += 1
                except Exception:
                    preview_err += 1
                    logger.exception(
                        "Goal intensity v5 preview failed today_fixture_id=%s", tid
                    )
            logger.info(
                "Goal intensity v5 preview post-scan job_id=%s ok=%s err=%s",
                job_id,
                preview_ok,
                preview_err,
            )
        except Exception:
            logger.exception(
                "Goal intensity v5 preview post-scan skipped job_id=%s", job_id
            )
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
                update_kwargs: dict[str, Any] = {
                    "status": JOB_STATUS_FAILED,
                    "finished_at": _utcnow(),
                    "current_step": "completed",
                    "errors_json": errs,
                }
                summary = _metrics_result_summary(metrics)
                if summary is not None:
                    update_kwargs["result_summary_json"] = summary
                update_scan_job(db, job_id, **update_kwargs)
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
                    update_kwargs = {
                        "status": JOB_STATUS_FAILED,
                        "finished_at": _utcnow(),
                        "current_step": "completed",
                        "errors_json": errs,
                    }
                    if job.result_summary_json is None:
                        summary = _metrics_result_summary(metrics)
                        if summary is not None:
                            update_kwargs["result_summary_json"] = summary
                    update_scan_job(db, job_id, **update_kwargs)
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

    try:
        check_api_budget_before_scan(db, usage_date=scan_date)
    except BudgetGuardStop as bg:
        return {
            "status": bg.status,
            "scan_date": scan_date.isoformat(),
            "message": bg.message,
            "details": bg.details,
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
