"""Job asincroni process-local per validazione Acquistabilità Fase 5.

Pattern allineato a cecchino_purchasability_research_jobs: ThreadPoolExecutor(1),
registry in-memory, risultati su /tmp. Persi su restart/deploy.
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

from app.core.database import SessionLocal
from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_validation import (
    PURCHASABILITY_VALIDATION_VERSION,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    PURCHASABILITY_PROMOTION_POLICY_VERSION,
    build_purchasability_promotion_readiness,
    build_purchasability_validation_summary,
)

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "completed", "failed"]

RESULT_DIR = Path(
    os.environ.get(
        "PURCHASABILITY_VALIDATION_JOB_DIR",
        "/tmp/cecchino_purchasability_validation",
    )
)
MAX_COMPLETED_JOBS = 5
TTL_COMPLETED_SECONDS = 6 * 3600
TTL_FAILED_SECONDS = 1 * 3600
POLL_AFTER_MS = 2000

_lock = threading.RLock()
_jobs: dict[str, "PurchasabilityValidationJob"] = {}
_executor: ThreadPoolExecutor | None = None
_initialized = False


class PurchasabilityValidationJobConflict(Exception):
    def __init__(self, active_job_id: str, active_filters: dict[str, Any]):
        self.active_job_id = active_job_id
        self.active_filters = active_filters
        super().__init__("purchasability_validation_job_already_running")


class PurchasabilityValidationJobNotFound(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__("validation_job_not_found_or_expired")


@dataclass
class PurchasabilityValidationJob:
    job_id: str
    status: JobStatus
    filters: dict[str, Any]
    filters_hash: str
    validation_version: str = PURCHASABILITY_VALIDATION_VERSION
    policy_version: str = PURCHASABILITY_PROMOTION_POLICY_VERSION
    created_at: str = field(default_factory=lambda: _utcnow_iso())
    started_at: str | None = None
    completed_at: str | None = None
    current_stage: str | None = None
    progress_message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_file_path: str | None = None
    summary_file_path: str | None = None
    _started_monotonic: float | None = field(default=None, repr=False)

    @property
    def elapsed_seconds(self) -> float | None:
        if self._started_monotonic is None:
            return None
        return max(0.0, time.monotonic() - self._started_monotonic)

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress_message": self.progress_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": (
                round(self.elapsed_seconds, 1) if self.elapsed_seconds is not None else None
            ),
            "filters": dict(self.filters),
            "validation_version": self.validation_version,
            "policy_version": self.policy_version,
            "result_available": self.status == "completed"
            and bool(self.result_file_path)
            and Path(self.result_file_path).is_file(),
            "result_file_path": self.result_file_path,
            "summary_file_path": self.summary_file_path,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "poll_after_ms": POLL_AFTER_MS,
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
            max_workers=1, thread_name_prefix="purch_val_job"
        )
        _initialized = True


def _parse_date(v: str | date | None) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    return date.fromisoformat(str(v)[:10])


def normalize_validation_filters(
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    promotion_eligible_only: bool = True,
) -> dict[str, Any]:
    return {
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "candidate_version": candidate_version or PURCHASABILITY_CANDIDATE_VERSION,
        "competition_id": competition_id,
        "market_key": market_key or None,
        "bootstrap_iterations": int(bootstrap_iterations),
        "promotion_eligible_only": bool(promotion_eligible_only),
    }


def filters_hash_for(filters: dict[str, Any]) -> str:
    raw = json.dumps(filters, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _active_job() -> PurchasabilityValidationJob | None:
    for job in _jobs.values():
        if job.status in ("queued", "running"):
            return job
    return None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(
        make_json_safe(payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _run_job(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = _utcnow_iso()
        job._started_monotonic = time.monotonic()
        job.current_stage = "loading"
        job.progress_message = "Caricamento coorte validazione…"

    db = SessionLocal()
    try:
        filters = job.filters
        date_from = _parse_date(filters.get("date_from"))
        date_to = _parse_date(filters.get("date_to"))
        if date_from is None or date_to is None:
            raise ValueError("date_from_and_date_to_required")

        with _lock:
            job.current_stage = "summary"
            job.progress_message = "Calcolo summary e residuali…"

        summary = build_purchasability_validation_summary(
            db,
            date_from=date_from,
            date_to=date_to,
            candidate_version=filters.get("candidate_version"),
            competition_id=filters.get("competition_id"),
            market_key=filters.get("market_key"),
            promotion_eligible_only=bool(
                filters.get("promotion_eligible_only", True)
            ),
            bootstrap_iterations=int(
                filters.get("bootstrap_iterations") or DEFAULT_BOOTSTRAP_ITERATIONS
            ),
        )

        with _lock:
            job.current_stage = "readiness"
            job.progress_message = "Valutazione gate promozione…"

        readiness = build_purchasability_promotion_readiness(
            db,
            date_from=date_from,
            date_to=date_to,
            candidate_version=filters.get("candidate_version"),
            competition_id=filters.get("competition_id"),
            market_key=filters.get("market_key"),
            bootstrap_iterations=int(
                filters.get("bootstrap_iterations") or DEFAULT_BOOTSTRAP_ITERATIONS
            ),
            promotion_eligible_only=bool(
                filters.get("promotion_eligible_only", True)
            ),
        )

        result = make_json_safe(
            {
                "status": "ok",
                "job_id": job_id,
                "validation_version": PURCHASABILITY_VALIDATION_VERSION,
                "policy_version": PURCHASABILITY_PROMOTION_POLICY_VERSION,
                "filters": filters,
                "summary": summary,
                "readiness": readiness,
                "jobs_persist_across_deploy": False,
            }
        )
        summary_payload = make_json_safe(
            {
                "status": "ok",
                "job_id": job_id,
                "readiness_status": readiness.get("status"),
                "eligible_for_manual_promotion": readiness.get(
                    "eligible_for_manual_promotion"
                ),
                "metrics": summary.get("metrics"),
                "temporal_span": summary.get("temporal_span"),
                "filters": filters,
            }
        )

        result_path = RESULT_DIR / f"{job_id}_result.json"
        summary_path = RESULT_DIR / f"{job_id}_summary.json"
        _atomic_write(result_path, result)
        _atomic_write(summary_path, summary_payload)

        with _lock:
            job.status = "completed"
            job.completed_at = _utcnow_iso()
            job.current_stage = "completed"
            job.progress_message = "Completato"
            job.result_file_path = str(result_path)
            job.summary_file_path = str(summary_path)
    except Exception as exc:
        logger.exception("purchasability_validation_job_failed job_id=%s", job_id)
        with _lock:
            job.status = "failed"
            job.completed_at = _utcnow_iso()
            job.current_stage = "failed"
            job.error_code = type(exc).__name__
            job.error_message = str(exc)[:500]
            job.progress_message = traceback.format_exc()[-400:]
    finally:
        db.close()


def start_purchasability_validation_job(
    *,
    date_from: date | str,
    date_to: date | str,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    promotion_eligible_only: bool = True,
) -> dict[str, Any]:
    _ensure_initialized()
    filters = normalize_validation_filters(
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        bootstrap_iterations=bootstrap_iterations,
        promotion_eligible_only=promotion_eligible_only,
    )
    fhash = filters_hash_for(filters)

    with _lock:
        active = _active_job()
        if active is not None:
            raise PurchasabilityValidationJobConflict(
                active.job_id, dict(active.filters)
            )
        job_id = str(uuid.uuid4())
        job = PurchasabilityValidationJob(
            job_id=job_id,
            status="queued",
            filters=filters,
            filters_hash=fhash,
            current_stage="queued",
            progress_message="In coda…",
        )
        _jobs[job_id] = job
        assert _executor is not None
        _executor.submit(_run_job, job_id)

    return {
        "job_id": job_id,
        "status": "queued",
        "poll_after_ms": POLL_AFTER_MS,
        "filters": filters,
    }


def get_purchasability_validation_job(job_id: str) -> dict[str, Any]:
    _ensure_initialized()
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise PurchasabilityValidationJobNotFound(job_id)
        return job.to_status_dict()


def get_purchasability_validation_job_result(job_id: str) -> dict[str, Any]:
    status = get_purchasability_validation_job(job_id)
    if status["status"] != "completed":
        raise PurchasabilityValidationJobNotFound(job_id)
    path = status.get("result_file_path") or (
        _jobs[job_id].result_file_path if job_id in _jobs else None
    )
    with _lock:
        job = _jobs.get(job_id)
        path = job.result_file_path if job else path
    if not path or not Path(path).is_file():
        raise PurchasabilityValidationJobNotFound(job_id)
    return json.loads(Path(path).read_text(encoding="utf-8"))
