"""Comando sincrono cron-ready per la scansione automatica Cecchino Today.

Uso:
  python -m app.jobs.cecchino_auto_scan --scheduled
  python -m app.jobs.cecchino_auto_scan --force-run
  python -m app.jobs.cecchino_auto_scan --force-run --target-date YYYY-MM-DD
  python -m app.jobs.cecchino_auto_scan --scheduled --dry-run
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models.cecchino_today_scan_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_FAILED_BUDGET_GUARD,
    JOB_STATUS_FAILED_TIMEOUT,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_PARTIAL_STOPPED_BUDGET,
    JOB_STATUS_PROVIDER_QUOTA_EXHAUSTED,
    JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_today_scan_job_service import (
    create_scan_job,
    execute_scan_job_sync,
    find_auto_scan_jobs_for_execution,
    get_any_active_scan_job,
    recover_stale_scan_jobs,
)
from app.services.cecchino.cecchino_today_scan_lock import (
    ScanLockNotAcquired,
    acquire_cecchino_scan_lock,
)

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_TIMEOUT = 2
EXIT_CONFIG = 3
EXIT_BUDGET = 4

SLOT_PRIMARY = "primary"
SLOT_RECOVERY = "recovery"

_abort_requested = False


def _request_abort(signum: int, _frame: Any) -> None:
    global _abort_requested
    _abort_requested = True
    logger.warning("Cecchino auto scan interruption requested signal=%s", signum)


def should_abort() -> bool:
    return _abort_requested


def install_signal_handlers() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _request_abort)
        except (ValueError, OSError):
            # Non disponibile in thread secondari / Windows edge cases
            pass


def _aware_now(now: datetime, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def local_execution_date(now: datetime, *, timezone_name: str) -> date:
    return _aware_now(now, timezone_name).date()


def resolve_target_scan_date(now: datetime, *, timezone_name: str) -> date:
    """Domani secondo il fuso indicato (default Europe/Rome)."""
    return local_execution_date(now, timezone_name=timezone_name) + timedelta(days=1)


def _minutes_of_day(hour: int, minute: int) -> int:
    return int(hour) * 60 + int(minute)


def _in_window(now_minutes: int, center: int, window_minutes: int) -> bool:
    return abs(now_minutes - center) <= int(window_minutes)


def resolve_auto_scan_slot(
    now: datetime,
    *,
    timezone_name: str,
    primary_hour: int,
    primary_minute: int,
    recovery_hour: int,
    recovery_minute: int,
    window_minutes: int,
) -> str | None:
    """Restituisce ``primary``, ``recovery`` o ``None`` (fuori finestra)."""
    local = _aware_now(now, timezone_name)
    now_minutes = _minutes_of_day(local.hour, local.minute)
    primary_center = _minutes_of_day(primary_hour, primary_minute)
    recovery_center = _minutes_of_day(recovery_hour, recovery_minute)

    in_primary = _in_window(now_minutes, primary_center, window_minutes)
    in_recovery = _in_window(now_minutes, recovery_center, window_minutes)

    if in_primary and in_recovery:
        # Preferisci primary se le finestre si sovrappongono
        return SLOT_PRIMARY
    if in_primary:
        return SLOT_PRIMARY
    if in_recovery:
        return SLOT_RECOVERY
    return None


def _auto_meta_from_job(job: CecchinoTodayScanJob) -> dict[str, Any] | None:
    summary = job.result_summary_json or {}
    if not isinstance(summary, dict):
        return None
    auto = summary.get("auto_scan")
    return auto if isinstance(auto, dict) else None


def _is_successful_auto_completion(job: CecchinoTodayScanJob) -> bool:
    if job.status != JOB_STATUS_COMPLETED:
        return False
    auto = _auto_meta_from_job(job)
    return bool(auto and auto.get("execution_source") == "auto_scan")


def _is_recoverable_auto_failure(job: CecchinoTodayScanJob) -> bool:
    if job.status in {
        JOB_STATUS_FAILED,
        JOB_STATUS_INTERRUPTED,
        JOB_STATUS_FAILED_TIMEOUT,
    }:
        return True
    if job.status == JOB_STATUS_PARTIAL_STOPPED_BUDGET:
        # Partial budget non è errore tecnico recuperabile con retry pieno
        return False
    if job.status == JOB_STATUS_FAILED_BUDGET_GUARD:
        return False
    return False


def evaluate_auto_scan_idempotency(
    jobs: list[CecchinoTodayScanJob],
    *,
    slot: str | None,
) -> dict[str, Any]:
    """Valuta se saltare l'esecuzione automatica.

    Returns:
        ``{action: run|skip, reason, reference_job_id?}``
    """
    completed = [j for j in jobs if _is_successful_auto_completion(j)]
    if completed:
        ref = completed[0]
        return {
            "action": "skip",
            "reason": "already_completed",
            "reference_job_id": ref.job_id,
            "reference_slot": (_auto_meta_from_job(ref) or {}).get("execution_slot"),
        }

    if slot == SLOT_RECOVERY:
        failed = [j for j in jobs if _is_recoverable_auto_failure(j)]
        if not jobs:
            return {"action": "run", "reason": "no_prior_auto_job"}
        if failed:
            return {
                "action": "run",
                "reason": "prior_auto_failed",
                "reference_job_id": failed[0].job_id,
            }
        # Solo job non-completati non falliti (es. skipped) → consentito
        return {"action": "run", "reason": "recovery_no_successful_primary"}

    return {"action": "run", "reason": "primary_or_force"}


def build_auto_scan_meta(
    *,
    execution_slot: str | None,
    target_date: date,
    timezone_name: str,
    local_execution_date_value: date,
    attempt: int,
    lock_acquired: bool,
    max_runtime_minutes: int,
) -> dict[str, Any]:
    return {
        "execution_source": "auto_scan",
        "execution_mode": "synchronous",
        "execution_slot": execution_slot,
        "target_date": target_date.isoformat(),
        "timezone": timezone_name,
        "local_execution_date": local_execution_date_value.isoformat(),
        "attempt": attempt,
        "lock_acquired": lock_acquired,
        "max_runtime_minutes": max_runtime_minutes,
    }


def outcome_to_exit_code(outcome: dict[str, Any]) -> int:
    status = str(outcome.get("status") or "")
    if status in {JOB_STATUS_COMPLETED, JOB_STATUS_SKIPPED_CONCURRENT_SCAN}:
        return EXIT_OK
    if status == JOB_STATUS_FAILED_TIMEOUT:
        return EXIT_TIMEOUT
    if status in {
        JOB_STATUS_PARTIAL_STOPPED_BUDGET,
        JOB_STATUS_FAILED_BUDGET_GUARD,
        JOB_STATUS_PROVIDER_QUOTA_EXHAUSTED,
    }:
        return EXIT_BUDGET
    if status in {JOB_STATUS_FAILED, JOB_STATUS_INTERRUPTED}:
        return EXIT_ERROR
    if outcome.get("noop"):
        return EXIT_OK
    return EXIT_ERROR


def _is_transient_retryable(outcome: dict[str, Any]) -> bool:
    if outcome.get("status") == JOB_STATUS_COMPLETED:
        return False
    if outcome.get("status") in {
        JOB_STATUS_PARTIAL_STOPPED_BUDGET,
        JOB_STATUS_FAILED_BUDGET_GUARD,
        JOB_STATUS_PROVIDER_QUOTA_EXHAUSTED,
        JOB_STATUS_FAILED_TIMEOUT,
        JOB_STATUS_SKIPPED_CONCURRENT_SCAN,
        JOB_STATUS_INTERRUPTED,
    }:
        return False
    if outcome.get("transient_candidate") is True:
        return True
    fixtures_checked = int(outcome.get("fixtures_checked") or 0)
    summary = outcome.get("result_summary") or {}
    api_total = 0
    if isinstance(summary, dict):
        api_total = int(summary.get("api_calls_total") or 0)
    if fixtures_checked > 0 or api_total > 0:
        return False
    return outcome.get("status") == JOB_STATUS_FAILED


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.jobs.cecchino_auto_scan",
        description="Scansione automatica sincrona Cecchino Today (cron-ready).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--scheduled",
        action="store_true",
        help="Modalità schedulata (enabled + finestra oraria Europe/Rome).",
    )
    mode.add_argument(
        "--force-run",
        action="store_true",
        help="Esecuzione manuale di test (ignora enabled e finestra oraria).",
    )
    parser.add_argument(
        "--target-date",
        type=str,
        default=None,
        help="Solo con --force-run: data target YYYY-MM-DD.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verifica config/slot/lock senza creare job né chiamare API.",
    )
    return parser.parse_args(argv)


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


def _install_posix_alarm(seconds: int) -> Callable[[], None]:
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        return lambda: None

    def _alarm_handler(signum: int, _frame: Any) -> None:
        global _abort_requested
        _abort_requested = True
        logger.error("POSIX SIGALRM fired — max runtime exceeded signal=%s", signum)
        raise ScanJobTimeoutFromAlarm()

    try:
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(int(seconds))
    except (ValueError, OSError):
        return lambda: None

    def _clear() -> None:
        try:
            signal.alarm(0)
        except (ValueError, OSError):
            pass

    return _clear


class ScanJobTimeoutFromAlarm(Exception):
    """Timeout via SIGALRM (solo POSIX)."""


def run_dry_run(
    *,
    settings: Any,
    now: datetime,
    scheduled: bool,
    force_run: bool,
    target_date: date,
    slot: str | None,
    local_date: date,
) -> int:
    logger.info(
        "cecchino_auto_scan dry-run enabled=%s timezone=%s target_date=%s "
        "local_execution_date=%s slot=%s scheduled=%s force_run=%s",
        settings.cecchino_auto_scan_enabled,
        settings.cecchino_auto_scan_timezone,
        target_date.isoformat(),
        local_date.isoformat(),
        slot,
        scheduled,
        force_run,
    )

    db = SessionLocal()
    try:
        recover_stale_scan_jobs(db)
        active = get_any_active_scan_job(db)
        auto_jobs = find_auto_scan_jobs_for_execution(
            db,
            target_date=target_date,
            local_execution_date=local_date,
        )
        idem = evaluate_auto_scan_idempotency(auto_jobs, slot=slot or SLOT_PRIMARY)
        logger.info(
            "dry-run db_ok=true active_job=%s auto_jobs=%s idempotency=%s",
            active.job_id if active else None,
            len(auto_jobs),
            idem,
        )
    except Exception:
        logger.exception("dry-run database check failed")
        return EXIT_ERROR
    finally:
        db.close()

    try:
        with acquire_cecchino_scan_lock(engine=engine) as payload:
            logger.info("dry-run lock_ok=true payload=%s", payload)
    except ScanLockNotAcquired as exc:
        logger.info("dry-run lock_ok=false payload=%s", exc.payload)
        return EXIT_OK
    except Exception:
        logger.exception("dry-run lock check failed")
        return EXIT_ERROR

    if scheduled and slot is None:
        logger.info("outside_scheduled_window dry-run")
    return EXIT_OK


def run_auto_scan(
    *,
    settings: Any,
    now: datetime,
    target_date: date,
    slot: str | None,
    local_date: date,
    force_run: bool,
) -> int:
    max_attempts = max(1, int(settings.cecchino_auto_scan_transient_attempts))
    retry_delay = max(0, int(settings.cecchino_auto_scan_transient_retry_delay_seconds))
    max_runtime_minutes = max(1, int(settings.cecchino_auto_scan_max_runtime_minutes))
    deadline = time.monotonic() + max_runtime_minutes * 60
    clear_alarm = _install_posix_alarm(max_runtime_minutes * 60)

    # Idempotenza (solo scheduled / non force con slot)
    db = SessionLocal()
    try:
        recover_stale_scan_jobs(db)
        auto_jobs = find_auto_scan_jobs_for_execution(
            db,
            target_date=target_date,
            local_execution_date=local_date,
        )
        if not force_run:
            idem = evaluate_auto_scan_idempotency(auto_jobs, slot=slot)
            if idem.get("action") == "skip":
                logger.info(
                    "cecchino_auto_scan already_completed target=%s local=%s slot=%s ref=%s",
                    target_date.isoformat(),
                    local_date.isoformat(),
                    slot,
                    idem.get("reference_job_id"),
                )
                return EXIT_OK
    finally:
        db.close()

    last_outcome: dict[str, Any] = {"status": JOB_STATUS_FAILED}

    try:
        for attempt in range(1, max_attempts + 1):
            if should_abort():
                logger.warning("abort before attempt=%s", attempt)
                return EXIT_ERROR
            if time.monotonic() >= deadline:
                logger.error("auto_scan_max_runtime_exceeded before attempt=%s", attempt)
                return EXIT_TIMEOUT

            logger.info(
                "cecchino_auto_scan attempt=%s/%s target=%s slot=%s",
                attempt,
                max_attempts,
                target_date.isoformat(),
                slot,
            )

            try:
                with acquire_cecchino_scan_lock(engine=engine) as lock_payload:
                    db = SessionLocal()
                    job_id: str | None = None
                    try:
                        recover_stale_scan_jobs(db)
                        active = get_any_active_scan_job(db)
                        if active is not None:
                            logger.info(
                                "skipped_concurrent_scan active_job=%s",
                                active.job_id,
                            )
                            return EXIT_OK

                        job = create_scan_job(
                            db,
                            scan_date=target_date,
                            timezone=settings.cecchino_auto_scan_timezone,
                            force_rescan=True,
                            execution_source="auto_scan",
                            execution_slot=slot,
                        )
                        job_id = job.job_id
                        auto_meta = build_auto_scan_meta(
                            execution_slot=slot,
                            target_date=target_date,
                            timezone_name=settings.cecchino_auto_scan_timezone,
                            local_execution_date_value=local_date,
                            attempt=attempt,
                            lock_acquired=True,
                            max_runtime_minutes=max_runtime_minutes,
                        )
                        auto_meta["lock"] = lock_payload

                        # Chiudi sessione di creazione: execute apre la propria
                        db.close()
                        db = None  # type: ignore[assignment]

                        last_outcome = execute_scan_job_sync(
                            job_id,
                            session_factory=SessionLocal,
                            execution_source="auto_scan",
                            acquire_lock=False,
                            auto_scan_meta=auto_meta,
                            deadline_monotonic=deadline,
                            should_abort=should_abort,
                        )
                    finally:
                        if db is not None:
                            try:
                                db.close()
                            except Exception:
                                pass
            except ScanLockNotAcquired as exc:
                logger.info(
                    "skipped_concurrent_scan lock_not_acquired payload=%s",
                    exc.payload,
                )
                return EXIT_OK
            except ScanJobTimeoutFromAlarm:
                logger.error("auto_scan_max_runtime_exceeded via SIGALRM")
                return EXIT_TIMEOUT

            exit_code = outcome_to_exit_code(last_outcome)
            if last_outcome.get("status") == JOB_STATUS_COMPLETED:
                return EXIT_OK
            if last_outcome.get("status") == JOB_STATUS_SKIPPED_CONCURRENT_SCAN:
                return EXIT_OK
            if last_outcome.get("status") == JOB_STATUS_FAILED_TIMEOUT:
                return EXIT_TIMEOUT
            if last_outcome.get("status") in {
                JOB_STATUS_PARTIAL_STOPPED_BUDGET,
                JOB_STATUS_FAILED_BUDGET_GUARD,
                JOB_STATUS_PROVIDER_QUOTA_EXHAUSTED,
            }:
                return EXIT_BUDGET
            if last_outcome.get("status") == JOB_STATUS_INTERRUPTED:
                return EXIT_ERROR

            if attempt < max_attempts and _is_transient_retryable(last_outcome):
                logger.warning(
                    "transient failure — retry after %ss attempt=%s outcome=%s",
                    retry_delay,
                    attempt,
                    last_outcome.get("status"),
                )
                time.sleep(retry_delay)
                continue

            return exit_code

        return outcome_to_exit_code(last_outcome)
    finally:
        clear_alarm()


def main(argv: list[str] | None = None) -> int:
    global _abort_requested
    _abort_requested = False
    _configure_logging()
    install_signal_handlers()

    args = _parse_args(argv)
    settings = get_settings()

    if args.target_date and not args.force_run:
        logger.error("--target-date è consentito solo insieme a --force-run")
        return EXIT_CONFIG

    timezone_name = settings.cecchino_auto_scan_timezone
    try:
        ZoneInfo(timezone_name)
    except Exception:
        logger.exception("timezone non valida: %s", timezone_name)
        return EXIT_CONFIG

    now = datetime.now(ZoneInfo(timezone_name))
    local_date = local_execution_date(now, timezone_name=timezone_name)

    if args.target_date:
        try:
            target_date = date.fromisoformat(args.target_date)
        except ValueError:
            logger.error("target-date non valido: %s", args.target_date)
            return EXIT_CONFIG
    else:
        target_date = resolve_target_scan_date(now, timezone_name=timezone_name)

    slot = resolve_auto_scan_slot(
        now,
        timezone_name=timezone_name,
        primary_hour=settings.cecchino_auto_scan_primary_hour,
        primary_minute=settings.cecchino_auto_scan_primary_minute,
        recovery_hour=settings.cecchino_auto_scan_recovery_hour,
        recovery_minute=settings.cecchino_auto_scan_recovery_minute,
        window_minutes=settings.cecchino_auto_scan_window_minutes,
    )

    if args.scheduled and not args.force_run:
        if not settings.cecchino_auto_scan_enabled:
            logger.info(
                "cecchino_auto_scan disabled (CECCHINO_AUTO_SCAN_ENABLED=false) — exit 0"
            )
            if args.dry_run:
                return run_dry_run(
                    settings=settings,
                    now=now,
                    scheduled=True,
                    force_run=False,
                    target_date=target_date,
                    slot=slot,
                    local_date=local_date,
                )
            return EXIT_OK
        if slot is None:
            logger.info("outside_scheduled_window now=%s tz=%s", now.isoformat(), timezone_name)
            if args.dry_run:
                return run_dry_run(
                    settings=settings,
                    now=now,
                    scheduled=True,
                    force_run=False,
                    target_date=target_date,
                    slot=None,
                    local_date=local_date,
                )
            return EXIT_OK

    if args.dry_run:
        return run_dry_run(
            settings=settings,
            now=now,
            scheduled=bool(args.scheduled),
            force_run=bool(args.force_run),
            target_date=target_date,
            slot=slot if args.scheduled else (slot or SLOT_PRIMARY),
            local_date=local_date,
        )

    effective_slot = slot
    if args.force_run and effective_slot is None:
        effective_slot = SLOT_PRIMARY

    logger.info(
        "cecchino_auto_scan start scheduled=%s force_run=%s target=%s slot=%s local=%s",
        args.scheduled,
        args.force_run,
        target_date.isoformat(),
        effective_slot,
        local_date.isoformat(),
    )

    try:
        return run_auto_scan(
            settings=settings,
            now=now,
            target_date=target_date,
            slot=effective_slot,
            local_date=local_date,
            force_run=bool(args.force_run),
        )
    except Exception:
        logger.exception("cecchino_auto_scan fatal error")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
