"""Job asincroni process-local per analisi empirica Balance v5 Step 2B.

ThreadPoolExecutor(max_workers=1), registry in-memory, risultati su
/tmp/cecchino_balance_v5_empirical_analysis. Persi su redeploy.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.services.cecchino.cecchino_balance_v5_empirical import (
    BALANCE_EMPIRICAL_DATASET_VERSION,
)
from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
    BALANCE_EMPIRICAL_ANALYSIS_VERSION,
    BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
    BOOTSTRAP_ITERATIONS_DEFAULT,
    BOOTSTRAP_ITERATIONS_MAX,
    BOOTSTRAP_ITERATIONS_MIN,
    build_balance_empirical_full_analysis,
    normalize_analysis_filters,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "completed", "failed"]

RESULT_DIR = Path(
    os.environ.get(
        "BALANCE_EMPIRICAL_ANALYSIS_JOB_DIR",
        "/tmp/cecchino_balance_v5_empirical_analysis",
    )
)
MAX_COMPLETED_JOBS = 5
TTL_COMPLETED_SECONDS = 6 * 3600
TTL_FAILED_SECONDS = 1 * 3600
POLL_AFTER_MS = 2000

_lock = threading.RLock()
_jobs: dict[str, "BalanceEmpiricalAnalysisJob"] = {}
_executor: ThreadPoolExecutor | None = None
_initialized = False


class BalanceEmpiricalAnalysisJobConflict(Exception):
    def __init__(self, active_job_id: str, active_filters: dict[str, Any]):
        self.active_job_id = active_job_id
        self.active_filters = active_filters
        super().__init__("balance_empirical_analysis_job_already_running")


class BalanceEmpiricalAnalysisJobNotFound(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__("analysis_job_not_found_or_expired")


@dataclass
class BalanceEmpiricalAnalysisJob:
    job_id: str
    status: JobStatus
    filters: dict[str, Any]
    filters_hash: str
    bootstrap_iterations: int
    analysis_version: str = BALANCE_EMPIRICAL_ANALYSIS_VERSION
    policy_version: str = BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION
    dataset_version: str = BALANCE_EMPIRICAL_DATASET_VERSION
    created_at: str = field(default_factory=lambda: _utcnow_iso())
    started_at: str | None = None
    completed_at: str | None = None
    current_stage: str | None = None
    progress_message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_file_path: str | None = None
    _started_monotonic: float | None = field(default=None, repr=False)

    def to_status_dict(self) -> dict[str, Any]:
        elapsed = None
        if self._started_monotonic is not None:
            elapsed = round(max(0.0, time.monotonic() - self._started_monotonic), 1)
        return {
            "job_id": self.job_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress_message": self.progress_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": elapsed,
            "filters": dict(self.filters),
            "bootstrap_iterations": self.bootstrap_iterations,
            "analysis_version": self.analysis_version,
            "policy_version": self.policy_version,
            "dataset_version": self.dataset_version,
            "result_available": self.status == "completed"
            and bool(self.result_file_path)
            and Path(self.result_file_path).is_file(),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "ephemeral_note": "I job possono essere persi al redeploy",
        }


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_initialized() -> None:
    global _executor, _initialized
    with _lock:
        if _initialized:
            return
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        _executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="bal_emp_analysis"
        )
        _initialized = True


def _parse_date(v: str | date | None) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    return date.fromisoformat(str(v)[:10])


def normalize_job_filters(
    *,
    date_from: date | str,
    date_to: date | str,
    competition_id: int | None = None,
    source_cohort: str | None = "all",
    country_name: str | None = None,
    f36_class: str | None = None,
    dominance_class: str | None = None,
    dominance_selection: str | None = None,
    draw_credibility_class: str | None = None,
    gap_class: str | None = None,
    bootstrap_iterations: int = BOOTSTRAP_ITERATIONS_DEFAULT,
) -> dict[str, Any]:
    iters = int(bootstrap_iterations)
    if iters < BOOTSTRAP_ITERATIONS_MIN or iters > BOOTSTRAP_ITERATIONS_MAX:
        raise ValueError(
            f"bootstrap_iterations must be in "
            f"[{BOOTSTRAP_ITERATIONS_MIN}, {BOOTSTRAP_ITERATIONS_MAX}]"
        )
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df is None or dt is None:
        raise ValueError("date_from and date_to required")
    base = normalize_analysis_filters(
        date_from=df,
        date_to=dt,
        competition_id=competition_id,
        source_cohort=source_cohort,
        country_name=country_name,
        f36_class=f36_class,
        dominance_class=dominance_class,
        dominance_selection=dominance_selection,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    base["bootstrap_iterations"] = iters
    return base


def filters_hash_for(filters: dict[str, Any]) -> str:
    payload = {
        **filters,
        "analysis_version": BALANCE_EMPIRICAL_ANALYSIS_VERSION,
        "policy_version": BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(
        make_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False
    )
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def enqueue_balance_empirical_analysis_job(filters: dict[str, Any]) -> dict[str, Any]:
    _ensure_initialized()
    fhash = filters_hash_for(filters)
    with _lock:
        for j in _jobs.values():
            if j.filters_hash == fhash and j.status in ("queued", "running", "completed"):
                if j.status == "completed" and (
                    not j.result_file_path or not Path(j.result_file_path).is_file()
                ):
                    continue
                return {
                    "status": j.status,
                    "job_id": j.job_id,
                    "reused": True,
                    "poll_after_ms": POLL_AFTER_MS,
                }
        active = next(
            (j for j in _jobs.values() if j.status in ("queued", "running")), None
        )
        if active is not None:
            raise BalanceEmpiricalAnalysisJobConflict(
                active.job_id, dict(active.filters)
            )
        job_id = str(uuid.uuid4())
        job = BalanceEmpiricalAnalysisJob(
            job_id=job_id,
            status="queued",
            filters=filters,
            filters_hash=fhash,
            bootstrap_iterations=int(filters["bootstrap_iterations"]),
            current_stage="queued",
            progress_message="In coda…",
        )
        _jobs[job_id] = job
        assert _executor is not None
        _executor.submit(_run_job_worker, job_id)
    logger.info(
        "balance_empirical_analysis_job_started job_id=%s filters_hash=%s",
        job_id,
        fhash[:12],
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "reused": False,
        "poll_after_ms": POLL_AFTER_MS,
    }


def get_balance_empirical_analysis_job(job_id: str) -> dict[str, Any]:
    _ensure_initialized()
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise BalanceEmpiricalAnalysisJobNotFound(job_id)
        status = job.to_status_dict()
        result = None
        if (
            job.status == "completed"
            and job.result_file_path
            and Path(job.result_file_path).is_file()
        ):
            result = json.loads(Path(job.result_file_path).read_text(encoding="utf-8"))
        status["result"] = result
        return status


def _run_job_worker(job_id: str) -> None:
    from app.core.database import SessionLocal

    db = None
    try:
        with _lock:
            j = _jobs.get(job_id)
            if j is None:
                return
            j.status = "running"
            j.started_at = _utcnow_iso()
            j._started_monotonic = time.monotonic()
            j.current_stage = "running"
            j.progress_message = "Analisi empirica in corso…"
            filters = dict(j.filters)
        db = SessionLocal()
        boot = int(filters.pop("bootstrap_iterations"))
        payload = build_balance_empirical_full_analysis(
            db, filters=filters, bootstrap_iterations=boot
        )
        out_path = RESULT_DIR / f"{job_id}.json"
        _atomic_write_json(out_path, payload)
        with _lock:
            j = _jobs.get(job_id)
            if j is None:
                return
            j.status = "completed"
            j.completed_at = _utcnow_iso()
            j.current_stage = "completed"
            j.progress_message = "Completato"
            j.result_file_path = str(out_path)
        logger.info("balance_empirical_analysis_job_completed job_id=%s", job_id)
    except Exception as exc:
        logger.exception("balance_empirical_analysis_job_failed job_id=%s", job_id)
        with _lock:
            j = _jobs.get(job_id)
            if j is not None:
                j.status = "failed"
                j.completed_at = _utcnow_iso()
                j.current_stage = "failed"
                j.error_code = type(exc).__name__
                j.error_message = str(exc)[:500]
                j.progress_message = "Fallito"
    finally:
        if db is not None:
            db.close()
        # trim old jobs
        with _lock:
            completed = [
                j
                for j in _jobs.values()
                if j.status in ("completed", "failed")
            ]
            completed.sort(key=lambda x: x.completed_at or x.created_at)
            while len(completed) > MAX_COMPLETED_JOBS:
                old = completed.pop(0)
                _jobs.pop(old.job_id, None)
