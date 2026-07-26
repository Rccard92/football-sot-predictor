"""Job asincrono / sincrono scan giornaliera Cecchino Today."""

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
    JOB_STATUS_FAILED_TIMEOUT,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
    CecchinoTodayScanJob,
)
from app.services.api_usage_context import BudgetGuardStop
from app.services.api_usage_service import check_api_budget_before_scan
from app.services.cecchino.cecchino_today_scan_lock import (
    ScanLockNotAcquired,
    acquire_cecchino_scan_lock,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics
from app.services.cecchino.cecchino_today_service import run_scan_day

logger = logging.getLogger(__name__)

STALE_JOB_MINUTES = 30
STALE_NO_PROGRESS_MINUTES = 5

DIAG_SKIPPED_CONCURRENT = "skipped_concurrent_scan"
DIAG_MAX_RUNTIME = "auto_scan_max_runtime_exceeded"
DIAG_INTERRUPTED = "interrupted"


class ScanJobTimeout(Exception):
    """Deadline complessiva del job superata."""


class ScanJobInterrupted(Exception):
    """Processo interrotto da SIGTERM/SIGINT."""


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


def get_any_active_scan_job(db: Session) -> CecchinoTodayScanJob | None:
    """Job attivo globale (qualsiasi data) — soft-check prima del lock."""
    return db.scalar(
        select(CecchinoTodayScanJob)
        .where(CecchinoTodayScanJob.status.in_(tuple(JOB_ACTIVE_STATUSES)))
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


def find_auto_scan_jobs_for_execution(
    db: Session,
    *,
    target_date: date,
    local_execution_date: date,
) -> list[CecchinoTodayScanJob]:
    """Job automatici per target_date con local_execution_date nel summary."""
    rows = list(
        db.scalars(
            select(CecchinoTodayScanJob)
            .where(CecchinoTodayScanJob.scan_date == target_date)
            .order_by(desc(CecchinoTodayScanJob.created_at)),
        ).all(),
    )
    out: list[CecchinoTodayScanJob] = []
    local_iso = local_execution_date.isoformat()
    target_iso = target_date.isoformat()
    for row in rows:
        summary = row.result_summary_json or {}
        auto = summary.get("auto_scan") if isinstance(summary, dict) else None
        if not isinstance(auto, dict):
            continue
        if auto.get("execution_source") != "auto_scan":
            continue
        if str(auto.get("local_execution_date") or "") != local_iso:
            continue
        if str(auto.get("target_date") or target_iso) != target_iso:
            continue
        out.append(row)
    return out


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


def make_progress_reporter(
    db: Session,
    job_id: str,
    *,
    deadline_monotonic: float | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Callable[..., None]:
    def progress(**kwargs: Any) -> None:
        if should_abort is not None and should_abort():
            raise ScanJobInterrupted(DIAG_INTERRUPTED)
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise ScanJobTimeout(DIAG_MAX_RUNTIME)

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


def _merge_auto_scan_meta(
    summary: dict[str, Any] | None,
    auto_scan_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if auto_scan_meta is None:
        return summary
    base = dict(summary or {})
    base["auto_scan"] = dict(auto_scan_meta)
    return base


def _mark_skipped_concurrent(
    db: Session,
    job_id: str,
    *,
    auto_scan_meta: dict[str, Any] | None,
    lock_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "diagnostic_code": DIAG_SKIPPED_CONCURRENT,
        "message": "Scansione concorrente già attiva — lock non acquisito",
    }
    if lock_payload:
        summary["lock"] = lock_payload
    summary = _merge_auto_scan_meta(summary, auto_scan_meta) or summary
    update_scan_job(
        db,
        job_id,
        status=JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
        finished_at=_utcnow(),
        current_step="completed",
        result_summary_json=summary,
        warnings_json=[DIAG_SKIPPED_CONCURRENT],
        errors_json=[],
    )
    db.commit()
    return {
        "status": JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
        "job_id": job_id,
        "diagnostic_code": DIAG_SKIPPED_CONCURRENT,
        "result_summary": summary,
    }


def _run_goal_intensity_preview(db: Session, job: CecchinoTodayScanJob, job_id: str) -> None:
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


def _execute_scan_job_body(
    db: Session,
    job_id: str,
    *,
    execution_source: str,
    auto_scan_meta: dict[str, Any] | None,
    deadline_monotonic: float | None,
    should_abort: Callable[[], bool] | None,
) -> dict[str, Any]:
    terminal = False
    metrics: ScanRunMetrics | None = None
    outcome: dict[str, Any] = {"status": JOB_STATUS_FAILED, "job_id": job_id}
    try:
        if should_abort is not None and should_abort():
            raise ScanJobInterrupted(DIAG_INTERRUPTED)
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise ScanJobTimeout(DIAG_MAX_RUNTIME)

        job = get_scan_job(db, job_id)
        if job is None:
            logger.warning("Cecchino scan job not found job_id=%s", job_id)
            return {"status": "not_found", "job_id": job_id}

        logger.info(
            "Cecchino scan job starting job_id=%s scan_date=%s source=%s",
            job_id,
            job.scan_date.isoformat(),
            execution_source,
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
        progress = make_progress_reporter(
            db,
            job_id,
            deadline_monotonic=deadline_monotonic,
            should_abort=should_abort,
        )
        report = run_scan_day(
            db,
            scan_date=job.scan_date,
            timezone=job.timezone,
            force_rescan=bool(job.force_rescan),
            job_id=job_id,
            progress=progress,
            metrics=metrics,
        )

        if should_abort is not None and should_abort():
            raise ScanJobInterrupted(DIAG_INTERRUPTED)
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise ScanJobTimeout(DIAG_MAX_RUNTIME)

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
            already_summary = (
                _merge_auto_scan_meta(already_summary, auto_scan_meta) or already_summary
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
            outcome = {
                "status": JOB_STATUS_COMPLETED,
                "job_id": job_id,
                "report_status": "already_scanned",
                "result_summary": already_summary,
            }
            return outcome

        if status != "ok":
            job_status = JOB_STATUS_FAILED
            if status in (JOB_STATUS_PARTIAL_STOPPED_BUDGET, JOB_STATUS_FAILED_BUDGET_GUARD):
                job_status = status
            summary = _merge_auto_scan_meta(
                _metrics_result_summary(metrics, report=report),
                auto_scan_meta,
            )
            update_scan_job(
                db,
                job_id,
                status=job_status,
                finished_at=_utcnow(),
                current_step="completed",
                errors_json=list(report.get("errors") or [report.get("message", "scan failed")]),
                warnings_json=list(report.get("warnings") or []),
                result_summary_json=summary,
                progress_current=int(report.get("fixtures_processed") or 0),
                progress_total=int(
                    report.get("fixtures_found") or report.get("total_discovered") or 0
                ),
                eligible_count=int(report.get("eligible") or 0),
                excluded_count=int(report.get("excluded_total") or 0),
                excluded_summary_json=dict(report.get("excluded_summary") or {}),
                fixtures_checked=int(report.get("fixtures_processed") or 0),
            )
            db.commit()
            terminal = True
            outcome = {
                "status": job_status,
                "job_id": job_id,
                "report_status": status,
                "result_summary": summary,
                "fixtures_checked": int(report.get("fixtures_processed") or 0),
            }
            return outcome

        summary = _merge_auto_scan_meta(
            _metrics_result_summary(metrics, report=report),
            auto_scan_meta,
        )
        update_scan_job(
            db,
            job_id,
            status=JOB_STATUS_COMPLETED,
            finished_at=_utcnow(),
            current_step="completed",
            progress_current=int(
                report.get("fixtures_processed") or report.get("total_discovered") or 0
            ),
            progress_total=int(
                report.get("fixtures_found") or report.get("total_discovered") or 0
            ),
            progress_pct=Decimal("100.0"),
            eligible_count=int(report.get("eligible") or 0),
            excluded_count=int(report.get("excluded_total") or 0),
            excluded_summary_json=dict(report.get("excluded_summary") or {}),
            result_summary_json=summary,
            warnings_json=list(report.get("warnings") or []),
            errors_json=list(report.get("errors") or []),
            fixtures_found=int(
                report.get("fixtures_found") or report.get("total_discovered") or 0
            ),
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
        _run_goal_intensity_preview(db, job, job_id)
        outcome = {
            "status": JOB_STATUS_COMPLETED,
            "job_id": job_id,
            "report_status": "ok",
            "result_summary": summary,
            "fixtures_checked": int(report.get("fixtures_processed") or 0),
        }
        return outcome
    except ScanJobTimeout as exc:
        logger.error("Cecchino scan job timeout job_id=%s: %s", job_id, exc)
        try:
            db.rollback()
            summary = _merge_auto_scan_meta(
                {
                    "diagnostic_code": DIAG_MAX_RUNTIME,
                    **(_metrics_result_summary(metrics) or {}),
                },
                auto_scan_meta,
            )
            update_scan_job(
                db,
                job_id,
                status=JOB_STATUS_FAILED_TIMEOUT,
                finished_at=_utcnow(),
                current_step="completed",
                errors_json=[DIAG_MAX_RUNTIME],
                result_summary_json=summary,
            )
            db.commit()
            terminal = True
            outcome = {
                "status": JOB_STATUS_FAILED_TIMEOUT,
                "job_id": job_id,
                "diagnostic_code": DIAG_MAX_RUNTIME,
            }
        except Exception:
            logger.exception("Failed to mark scan job timeout job_id=%s", job_id)
        return outcome
    except ScanJobInterrupted as exc:
        logger.warning("Cecchino scan job interrupted job_id=%s: %s", job_id, exc)
        try:
            db.rollback()
            summary = _merge_auto_scan_meta(
                {
                    "diagnostic_code": DIAG_INTERRUPTED,
                    **(_metrics_result_summary(metrics) or {}),
                },
                auto_scan_meta,
            )
            update_scan_job(
                db,
                job_id,
                status=JOB_STATUS_INTERRUPTED,
                finished_at=_utcnow(),
                current_step="completed",
                errors_json=[DIAG_INTERRUPTED],
                result_summary_json=summary,
            )
            db.commit()
            terminal = True
            outcome = {
                "status": JOB_STATUS_INTERRUPTED,
                "job_id": job_id,
                "diagnostic_code": DIAG_INTERRUPTED,
            }
        except Exception:
            logger.exception("Failed to mark scan job interrupted job_id=%s", job_id)
        return outcome
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
                summary = _merge_auto_scan_meta(
                    _metrics_result_summary(metrics),
                    auto_scan_meta,
                )
                if summary is not None:
                    update_kwargs["result_summary_json"] = summary
                update_scan_job(db, job_id, **update_kwargs)
                db.commit()
                terminal = True
                outcome = {
                    "status": JOB_STATUS_FAILED,
                    "job_id": job_id,
                    "error": str(exc)[:500],
                    "fixtures_checked": int(job.fixtures_checked or 0),
                    "transient_candidate": int(job.fixtures_checked or 0) == 0,
                }
        except Exception:
            logger.exception("Failed to mark scan job as failed job_id=%s", job_id)
        return outcome
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
                        summary = _merge_auto_scan_meta(
                            _metrics_result_summary(metrics),
                            auto_scan_meta,
                        )
                        if summary is not None:
                            update_kwargs["result_summary_json"] = summary
                    update_scan_job(db, job_id, **update_kwargs)
                    db.commit()
                    outcome = {
                        "status": JOB_STATUS_FAILED,
                        "job_id": job_id,
                        "diagnostic_code": "non_terminal_guard",
                    }
            except Exception:
                logger.exception("Failed guard cleanup for scan job job_id=%s", job_id)


def execute_scan_job_sync(
    job_id: str,
    *,
    session_factory=SessionLocal,
    execution_source: str = "manual",
    acquire_lock: bool = True,
    auto_scan_meta: dict[str, Any] | None = None,
    deadline_monotonic: float | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Lifecycle sincrono condiviso (thread manuale + comando auto scan)."""
    db = session_factory()
    try:
        if acquire_lock:
            try:
                with acquire_cecchino_scan_lock() as lock_payload:
                    meta = dict(auto_scan_meta or {}) if auto_scan_meta else None
                    if meta is not None:
                        meta["lock_acquired"] = True
                        meta["lock"] = lock_payload
                    return _execute_scan_job_body(
                        db,
                        job_id,
                        execution_source=execution_source,
                        auto_scan_meta=meta,
                        deadline_monotonic=deadline_monotonic,
                        should_abort=should_abort,
                    )
            except ScanLockNotAcquired as exc:
                return _mark_skipped_concurrent(
                    db,
                    job_id,
                    auto_scan_meta=auto_scan_meta,
                    lock_payload=exc.payload,
                )
        return _execute_scan_job_body(
            db,
            job_id,
            execution_source=execution_source,
            auto_scan_meta=auto_scan_meta,
            deadline_monotonic=deadline_monotonic,
            should_abort=should_abort,
        )
    finally:
        db.close()


def _run_scan_job_thread(job_id: str) -> None:
    execute_scan_job_sync(
        job_id,
        execution_source="manual",
        acquire_lock=True,
    )


def create_scan_job(
    db: Session,
    *,
    scan_date: date,
    timezone: str,
    force_rescan: bool,
    execution_source: str = "manual",
    execution_slot: str | None = None,
) -> CecchinoTodayScanJob:
    """Crea un job in stato queued senza avviare il runner."""
    job_id = str(uuid.uuid4())
    initial_summary: dict[str, Any] | None = None
    if execution_source == "auto_scan":
        initial_summary = {
            "auto_scan": {
                "execution_source": "auto_scan",
                "execution_mode": "synchronous",
                "execution_slot": execution_slot,
                "target_date": scan_date.isoformat(),
                "timezone": timezone,
            }
        }
    job = CecchinoTodayScanJob(
        job_id=job_id,
        scan_date=scan_date,
        timezone=timezone,
        force_rescan=force_rescan,
        status=JOB_STATUS_QUEUED,
        current_step="fetching_fixtures",
        result_summary_json=initial_summary,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


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

    job = create_scan_job(
        db,
        scan_date=scan_date,
        timezone=timezone,
        force_rescan=force_rescan,
        execution_source="manual",
        execution_slot=None,
    )

    thread = threading.Thread(
        target=_run_scan_job_thread,
        args=(job.job_id,),
        daemon=True,
        name=f"cecchino-scan-{job.job_id[:8]}",
    )
    thread.start()

    return {
        "job_id": job.job_id,
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
