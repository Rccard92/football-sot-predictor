"""Job asincroni process-local per ricerca statistica Acquistabilità (Fase 2A.3).

Infrastruttura tecnica: ThreadPoolExecutor(max_workers=1), registry in-memory,
risultati su /tmp. I job si perdono su restart/deploy. Nessuna migration/Redis/Celery.
La versione statistica resta cecchino_purchasability_statistical_research_v2a_2.
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.services.cecchino.cecchino_purchasability_audit import (
    DATASET_VERSION,
    make_json_safe,
)
from app.services.cecchino.cecchino_purchasability_statistical_research import (
    STAT_VERSION,
    build_purchasability_statistical_research,
)

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "completed", "failed"]

RESULT_DIR = Path(
    os.environ.get(
        "PURCHASABILITY_RESEARCH_JOB_DIR",
        "/tmp/cecchino_purchasability_research",
    )
)
MAX_COMPLETED_JOBS = 5
TTL_COMPLETED_SECONDS = 6 * 3600
TTL_FAILED_SECONDS = 1 * 3600
POLL_AFTER_MS = 2000

SUMMARY_KEYS = (
    "status",
    "version",
    "dataset_version",
    "cohort_identity",
    "data_quality",
    "book_baseline_assessment",
    "candidate_specifications",
    "feature_decisions",
    "rating_benchmark",
    "phase_2b_readiness",
    "limitations",
    "elapsed_ms",
    "filters",
    "research_banner",
    "no_db_writes",
    "no_purchasability_formula",
)

STAGE_MESSAGES = {
    "loading_dataset": "Caricamento dataset settled_core…",
    "feature_engineering": "Feature engineering e filtro coorte…",
    "temporal_cv": "CV temporale per mercato…",
    "paired_bootstrap": "Confronti paired e bootstrap…",
    "cross_market_analysis": "Analisi stabilità cross-market…",
    "building_payload": "Costruzione payload di readiness…",
    "serializing_result": "Serializzazione JSON…",
    "completed": "Completato",
}

_lock = threading.RLock()
_jobs: dict[str, "PurchasabilityResearchJob"] = {}
_executor: ThreadPoolExecutor | None = None
_initialized = False


class PurchasabilityResearchJobConflict(Exception):
    def __init__(self, active_job_id: str, active_filters: dict[str, Any]):
        self.active_job_id = active_job_id
        self.active_filters = active_filters
        super().__init__("purchasability_research_job_already_running")


class PurchasabilityResearchJobNotFound(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__("research_job_not_found_or_expired")


@dataclass
class PurchasabilityResearchJob:
    job_id: str
    status: JobStatus
    filters: dict[str, Any]
    filters_hash: str
    statistical_version: str = STAT_VERSION
    dataset_version: str = DATASET_VERSION
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
        if self.status in ("completed", "failed") and self.completed_at:
            # freeze at completion
            try:
                end = datetime.fromisoformat(self.completed_at.replace("Z", "+00:00"))
                start = datetime.fromisoformat(
                    (self.started_at or self.created_at).replace("Z", "+00:00")
                )
                return max(0.0, (end - start).total_seconds())
            except Exception:
                return time.monotonic() - self._started_monotonic
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
            "statistical_version": self.statistical_version,
            "dataset_version": self.dataset_version,
            "result_available": self.status == "completed"
            and bool(self.result_file_path)
            and Path(self.result_file_path).is_file(),
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_initialized() -> None:
    global _executor, _initialized
    with _lock:
        if _initialized:
            return
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="purch_stat_job")
        _initialized = True
        cleanup_expired_jobs()
        logger.info(
            "purchasability_research_job_cleanup",
            extra={"event": "purchasability_research_job_cleanup", "phase": "init"},
        )


def filters_hash_for(
    *,
    date_from: date | str | None,
    date_to: date | str | None,
    competition_id: int | None,
    market_family: str | None,
    selection: str | None,
    bootstrap_iterations: int,
    seed: int,
    statistical_version: str = STAT_VERSION,
) -> str:
    payload = {
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "competition_id": competition_id,
        "market_family": market_family or None,
        "selection": selection or None,
        "bootstrap_iterations": int(bootstrap_iterations),
        "seed": int(seed),
        "statistical_version": statistical_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_filters(
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    selection: str | None = None,
    bootstrap_iterations: int = 200,
    seed: int = 42,
) -> dict[str, Any]:
    return {
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "competition_id": competition_id,
        "market_family": market_family or None,
        "selection": selection or None,
        "bootstrap_iterations": int(bootstrap_iterations),
        "seed": int(seed),
    }


def _parse_date(v: str | date | None) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    return date.fromisoformat(str(v)[:10])


def _job_age_seconds(job: PurchasabilityResearchJob) -> float:
    ref = job.completed_at or job.created_at
    try:
        ts = datetime.fromisoformat(ref.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except Exception:
        return 0.0


def _unlink_quiet(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_expired_jobs() -> dict[str, int]:
    """Elimina metadata scaduti, file scaduti e .tmp orfani. Solo RESULT_DIR."""
    _ensure_dir()
    removed_jobs = 0
    removed_files = 0
    with _lock:
        to_drop: list[str] = []
        completed = [
            j for j in _jobs.values() if j.status == "completed"
        ]
        # Keep newest MAX_COMPLETED_JOBS completed
        completed.sort(key=lambda j: j.completed_at or j.created_at, reverse=True)
        for j in completed[MAX_COMPLETED_JOBS:]:
            to_drop.append(j.job_id)

        for jid, j in list(_jobs.items()):
            age = _job_age_seconds(j)
            if j.status == "completed" and age > TTL_COMPLETED_SECONDS:
                to_drop.append(jid)
            elif j.status == "failed" and age > TTL_FAILED_SECONDS:
                to_drop.append(jid)

        for jid in set(to_drop):
            j = _jobs.pop(jid, None)
            if j:
                _unlink_quiet(j.result_file_path)
                _unlink_quiet(j.summary_file_path)
                removed_jobs += 1

        # orphan tmp / expired files by mtime
        now = time.time()
        if RESULT_DIR.is_dir():
            for p in RESULT_DIR.iterdir():
                try:
                    if not p.is_file():
                        continue
                    age = now - p.stat().st_mtime
                    if p.suffix == ".tmp" or p.name.endswith(".tmp"):
                        p.unlink(missing_ok=True)
                        removed_files += 1
                        continue
                    # drop files without live job after TTL
                    stem = p.name.split(".")[0]
                    if stem not in _jobs and age > TTL_COMPLETED_SECONDS:
                        p.unlink(missing_ok=True)
                        removed_files += 1
                except OSError:
                    continue

    logger.info(
        "purchasability_research_job_cleanup removed_jobs=%s removed_files=%s",
        removed_jobs,
        removed_files,
    )
    return {"removed_jobs": removed_jobs, "removed_files": removed_files}


def _ensure_dir() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: Any) -> None:
    """Strict JSON → .tmp → fsync → rename atomico."""
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def build_summary_payload(full: dict[str, Any]) -> dict[str, Any]:
    return {k: full.get(k) for k in SUMMARY_KEYS if k in full or k in (
        "status", "version", "dataset_version", "filters", "elapsed_ms",
        "phase_2b_readiness", "limitations",
    )}


def get_active_job() -> PurchasabilityResearchJob | None:
    _ensure_initialized()
    with _lock:
        for j in _jobs.values():
            if j.status in ("queued", "running"):
                return j
    return None


def get_job(job_id: str) -> PurchasabilityResearchJob:
    _ensure_initialized()
    with _lock:
        j = _jobs.get(job_id)
        if j is None:
            raise PurchasabilityResearchJobNotFound(job_id)
        return j


def enqueue_purchasability_research_job(
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    selection: str | None = None,
    bootstrap_iterations: int = 200,
    seed: int = 42,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Avvia o riusa un job. Ritorna dict per HTTP 202. Raise conflict se altro job attivo."""
    _ensure_initialized()
    cleanup_expired_jobs()

    filters = normalize_filters(
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        selection=selection,
        bootstrap_iterations=bootstrap_iterations,
        seed=seed,
    )
    fhash = filters_hash_for(**filters, statistical_version=STAT_VERSION)

    with _lock:
        # reuse identical running/queued
        for j in _jobs.values():
            if j.filters_hash == fhash and j.status in ("queued", "running"):
                logger.info(
                    "purchasability_research_job_reused job_id=%s status=%s",
                    j.job_id,
                    j.status,
                )
                return {
                    "status": j.status,
                    "job_id": j.job_id,
                    "reused": True,
                    "poll_after_ms": POLL_AFTER_MS,
                }
            if (
                j.filters_hash == fhash
                and j.status == "completed"
                and j.result_file_path
                and Path(j.result_file_path).is_file()
            ):
                logger.info(
                    "purchasability_research_job_reused job_id=%s status=completed",
                    j.job_id,
                )
                return {
                    "status": "completed",
                    "job_id": j.job_id,
                    "reused": True,
                    "poll_after_ms": POLL_AFTER_MS,
                }

        active = next((j for j in _jobs.values() if j.status in ("queued", "running")), None)
        if active is not None:
            logger.info(
                "purchasability_research_job_conflict active_job_id=%s",
                active.job_id,
            )
            raise PurchasabilityResearchJobConflict(active.job_id, dict(active.filters))

        job_id = str(uuid.uuid4())
        job = PurchasabilityResearchJob(
            job_id=job_id,
            status="queued",
            filters=filters,
            filters_hash=fhash,
            current_stage="queued",
            progress_message="In coda…",
        )
        _jobs[job_id] = job
        assert _executor is not None
        _executor.submit(_run_job_worker, job_id, rows)

    logger.info("purchasability_research_job_started job_id=%s filters_hash=%s", job_id, fhash[:12])
    return {
        "status": "queued",
        "job_id": job_id,
        "reused": False,
        "poll_after_ms": POLL_AFTER_MS,
    }


def _update_progress(job_id: str, stage: str, meta: dict[str, Any]) -> None:
    with _lock:
        j = _jobs.get(job_id)
        if j is None or j.status not in ("queued", "running"):
            return
        j.current_stage = stage
        j.progress_message = STAGE_MESSAGES.get(stage, stage)
        if meta.get("market"):
            j.progress_message = f"{j.progress_message} ({meta['market']})"
    logger.info(
        "purchasability_research_job_stage job_id=%s stage=%s",
        job_id,
        stage,
    )


def _run_job_worker(job_id: str, rows: list[dict[str, Any]] | None) -> None:
    from app.core.database import SessionLocal

    db = None
    payload: dict[str, Any] | None = None
    try:
        with _lock:
            j = _jobs.get(job_id)
            if j is None:
                return
            j.status = "running"
            j.started_at = _utcnow_iso()
            j._started_monotonic = time.monotonic()
            j.current_stage = "loading_dataset"
            j.progress_message = STAGE_MESSAGES["loading_dataset"]
            filters = dict(j.filters)

        db = SessionLocal()

        def progress_cb(stage: str, meta: dict[str, Any]) -> None:
            _update_progress(job_id, stage, meta)

        payload = build_purchasability_statistical_research(
            db,
            date_from=_parse_date(filters.get("date_from")),
            date_to=_parse_date(filters.get("date_to")),
            competition_id=filters.get("competition_id"),
            market_family=filters.get("market_family"),
            selection=filters.get("selection"),
            bootstrap_iterations=int(filters.get("bootstrap_iterations") or 200),
            seed=int(filters.get("seed") or 42),
            rows=rows,
            progress_callback=progress_cb,
        )

        _update_progress(job_id, "serializing_result", {})
        safe = make_json_safe(payload)
        # strict validate
        json.dumps(safe, allow_nan=False)

        result_path = RESULT_DIR / f"{job_id}.result.json"
        summary_path = RESULT_DIR / f"{job_id}.summary.json"
        summary = build_summary_payload(safe)
        # ensure required summary keys
        for k in (
            "status",
            "version",
            "dataset_version",
            "phase_2b_readiness",
            "filters",
            "elapsed_ms",
            "limitations",
        ):
            if k not in summary:
                summary[k] = safe.get(k)

        atomic_write_json(result_path, safe)
        atomic_write_json(summary_path, summary)

        with _lock:
            j = _jobs.get(job_id)
            if j is None:
                return
            j.result_file_path = str(result_path)
            j.summary_file_path = str(summary_path)
            j.status = "completed"
            j.completed_at = _utcnow_iso()
            j.current_stage = "completed"
            j.progress_message = STAGE_MESSAGES["completed"]

        logger.info(
            "purchasability_research_job_completed job_id=%s result=%s summary=%s",
            job_id,
            result_path.name,
            summary_path.name,
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception(
            "purchasability_research_job_failed job_id=%s error=%s\n%s",
            job_id,
            e,
            tb,
        )
        with _lock:
            j = _jobs.get(job_id)
            if j is not None:
                j.status = "failed"
                j.completed_at = _utcnow_iso()
                j.error_code = "purchasability_research_job_failed"
                j.error_message = str(e)[:500]
                j.current_stage = "failed"
                j.progress_message = "Elaborazione fallita"
                if j._started_monotonic is None:
                    j._started_monotonic = time.monotonic()
    finally:
        payload = None
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        gc.collect()


def reset_jobs_for_tests() -> None:
    """Solo test: svuota registry (non spegne l'executor)."""
    global _initialized
    with _lock:
        for j in list(_jobs.values()):
            _unlink_quiet(j.result_file_path)
            _unlink_quiet(j.summary_file_path)
        _jobs.clear()


def set_result_dir_for_tests(path: Path) -> None:
    global RESULT_DIR, _initialized
    with _lock:
        RESULT_DIR = Path(path)
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
