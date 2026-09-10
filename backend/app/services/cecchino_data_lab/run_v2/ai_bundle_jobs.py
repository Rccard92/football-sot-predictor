"""Job asincroni per pacchetto AI RUN V2 — disk sidecar, recoverable, TTL.

DB = source of truth dei dati. ZIP/sidecar = cache rigenerabile sotto
`/tmp/cecchino_run_v2_ai_exports` (override via RUN_V2_AI_EXPORT_DIR).

Idempotenza: (run_id, export_schema_version).
Dopo restart: job `building` su sidecar → `interrupted` + retryable.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.core.database import SessionLocal
from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.services.cecchino_data_lab.run_v2.constants import RUN_V2_EXPORT_SCHEMA_VERSION

logger = logging.getLogger(__name__)

JobStatus = Literal["pending", "building", "ready", "failed", "interrupted"]

RESULT_DIR = Path(
    os.environ.get("RUN_V2_AI_EXPORT_DIR", "/tmp/cecchino_run_v2_ai_exports")
)
TTL_READY_SECONDS = int(os.environ.get("RUN_V2_AI_EXPORT_TTL_SECONDS", str(24 * 3600)))
TTL_FAILED_SECONDS = int(os.environ.get("RUN_V2_AI_EXPORT_FAILED_TTL_SECONDS", str(6 * 3600)))
MAX_CACHE_BYTES = int(
    os.environ.get("RUN_V2_AI_EXPORT_MAX_CACHE_BYTES", str(2 * 1024 * 1024 * 1024))
)
POLL_AFTER_MS = 2000

_lock = threading.RLock()
_jobs: dict[str, "AiBundleExportJob"] = {}
_key_to_job: dict[str, str] = {}
_executor: ThreadPoolExecutor | None = None
_initialized = False


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(run_id: int, schema_version: str = RUN_V2_EXPORT_SCHEMA_VERSION) -> str:
    return f"{int(run_id)}__{schema_version}"


def _job_dir(run_id: int, schema_version: str = RUN_V2_EXPORT_SCHEMA_VERSION) -> Path:
    return RESULT_DIR / _cache_key(run_id, schema_version)


def _sidecar_path(job_dir: Path) -> Path:
    return job_dir / "job.json"


def _zip_path(job_dir: Path) -> Path:
    return job_dir / "ai_bundle.zip"


def _ensure_executor() -> ThreadPoolExecutor:
    global _executor, _initialized
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="run_v2_ai_export")
        if not _initialized:
            _recover_sidecars()
            _initialized = True
        return _executor


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _load_sidecar(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _write_sidecar(job_dir: Path, payload: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    tmp = job_dir / "job.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(_sidecar_path(job_dir))


def _parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def purge_expired_cache(*, now: float | None = None) -> list[str]:
    """Cancella solo artefatti sotto RESULT_DIR (rigenerabili)."""
    now_ts = now if now is not None else time.time()
    removed: list[str] = []
    if not RESULT_DIR.exists():
        return removed

    entries: list[tuple[float, Path, dict[str, Any]]] = []
    for child in RESULT_DIR.iterdir():
        if not child.is_dir():
            continue
        sc = _load_sidecar(_sidecar_path(child)) or {}
        status = str(sc.get("status") or "")
        finished = _parse_iso(sc.get("completed_at") or sc.get("updated_at") or sc.get("created_at"))
        age_base = finished if finished is not None else child.stat().st_mtime
        ttl = TTL_READY_SECONDS if status == "ready" else TTL_FAILED_SECONDS
        if status in ("ready", "failed", "interrupted") and (now_ts - age_base) > ttl:
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)
            continue
        entries.append((age_base, child, sc))

    total = _dir_size_bytes(RESULT_DIR)
    if total <= MAX_CACHE_BYTES:
        return removed

    # Size cap: elimina i più vecchi ready/failed/interrupted (mai building attivo).
    candidates = sorted(
        (
            (age, path)
            for age, path, sc in entries
            if str(sc.get("status") or "") in ("ready", "failed", "interrupted")
        ),
        key=lambda t: t[0],
    )
    for _age, path in candidates:
        if total <= MAX_CACHE_BYTES:
            break
        size = _dir_size_bytes(path)
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
        total = max(0, total - size)
    return removed


def _recover_sidecars() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    purge_expired_cache()
    for child in RESULT_DIR.iterdir():
        if not child.is_dir():
            continue
        sc = _load_sidecar(_sidecar_path(child))
        if not sc:
            continue
        run_id = int(sc.get("run_id") or 0)
        schema = str(sc.get("export_schema_version") or RUN_V2_EXPORT_SCHEMA_VERSION)
        job_id = str(sc.get("job_id") or child.name)
        status = str(sc.get("status") or "")
        if status in ("pending", "building"):
            status = "interrupted"
            sc["status"] = status
            sc["retryable"] = True
            sc["error_code"] = sc.get("error_code") or "worker_restart"
            sc["error_message"] = sc.get("error_message") or (
                "Worker restart: job interrotto; ritentare create."
            )
            sc["updated_at"] = _utcnow_iso()
            _write_sidecar(child, sc)
        job = AiBundleExportJob.from_sidecar(sc, job_dir=child)
        _jobs[job_id] = job
        _key_to_job[_cache_key(run_id, schema)] = job_id


def read_cached_export_counts(run_id: int) -> dict[str, Any] | None:
    _ensure_executor()
    job_dir = _job_dir(int(run_id))
    sc = _load_sidecar(_sidecar_path(job_dir))
    if not sc or sc.get("status") != "ready":
        return None
    counts = sc.get("export_counts")
    return counts if isinstance(counts, dict) else None


@dataclass
class AiBundleExportJob:
    job_id: str
    run_id: int
    export_schema_version: str
    status: JobStatus
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    started_at: str | None = None
    completed_at: str | None = None
    phase: str | None = None
    progress_pct: float = 0.0
    progress_message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    filename: str | None = None
    zip_bytes: int | None = None
    export_counts: dict[str, Any] = field(default_factory=dict)
    job_dir: str = ""
    _started_monotonic: float | None = field(default=None, repr=False)

    @classmethod
    def from_sidecar(cls, sc: dict[str, Any], *, job_dir: Path) -> "AiBundleExportJob":
        return cls(
            job_id=str(sc["job_id"]),
            run_id=int(sc["run_id"]),
            export_schema_version=str(
                sc.get("export_schema_version") or RUN_V2_EXPORT_SCHEMA_VERSION
            ),
            status=sc.get("status") or "interrupted",  # type: ignore[arg-type]
            created_at=str(sc.get("created_at") or _utcnow_iso()),
            updated_at=str(sc.get("updated_at") or _utcnow_iso()),
            started_at=sc.get("started_at"),
            completed_at=sc.get("completed_at"),
            phase=sc.get("phase"),
            progress_pct=float(sc.get("progress_pct") or 0.0),
            progress_message=sc.get("progress_message"),
            error_code=sc.get("error_code"),
            error_message=sc.get("error_message"),
            retryable=bool(sc.get("retryable")),
            filename=sc.get("filename"),
            zip_bytes=sc.get("zip_bytes"),
            export_counts=dict(sc.get("export_counts") or {}),
            job_dir=str(job_dir),
        )

    def to_sidecar(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "export_schema_version": self.export_schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "phase": self.phase,
            "progress_pct": self.progress_pct,
            "progress_message": self.progress_message,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "filename": self.filename,
            "zip_bytes": self.zip_bytes,
            "export_counts": self.export_counts,
            "zip_path": str(_zip_path(Path(self.job_dir))) if self.job_dir else None,
        }

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "export_schema_version": self.export_schema_version,
            "status": self.status,
            "phase": self.phase,
            "progress_pct": round(float(self.progress_pct), 1),
            "progress_message": self.progress_message,
            "retryable": self.retryable,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "filename": self.filename,
            "zip_bytes": self.zip_bytes,
            "export_counts": self.export_counts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "poll_after_ms": POLL_AFTER_MS,
            "download_ready": self.status == "ready" and bool(self.filename),
        }

    def persist(self) -> None:
        self.updated_at = _utcnow_iso()
        if not self.job_dir:
            self.job_dir = str(_job_dir(self.run_id, self.export_schema_version))
        _write_sidecar(Path(self.job_dir), self.to_sidecar())


def get_job(job_id: str) -> AiBundleExportJob | None:
    _ensure_executor()
    with _lock:
        return _jobs.get(job_id)


def get_job_for_run(
    run_id: int, *, schema_version: str = RUN_V2_EXPORT_SCHEMA_VERSION
) -> AiBundleExportJob | None:
    _ensure_executor()
    with _lock:
        jid = _key_to_job.get(_cache_key(int(run_id), schema_version))
        return _jobs.get(jid) if jid else None


def create_or_reuse_job(run_id: int) -> AiBundleExportJob:
    """Idempotente per run_id + export_schema_version."""
    executor = _ensure_executor()
    purge_expired_cache()
    schema = RUN_V2_EXPORT_SCHEMA_VERSION
    key = _cache_key(int(run_id), schema)

    with _lock:
        existing_id = _key_to_job.get(key)
        existing = _jobs.get(existing_id) if existing_id else None
        if existing is not None:
            zip_file = _zip_path(Path(existing.job_dir)) if existing.job_dir else None
            if existing.status == "ready" and zip_file and zip_file.is_file():
                return existing
            if existing.status in ("pending", "building"):
                return existing
            # failed / interrupted → nuovo job (stessa directory cache)

        db = SessionLocal()
        try:
            run = db.get(CecchinoRunV2Run, int(run_id))
            if run is None:
                raise ValueError(f"run_v2 {run_id} inesistente")
            if str(run.status) != "completed":
                raise ValueError(f"run_v2 {run_id} non completed (status={run.status})")
        finally:
            db.close()

        job_dir = _job_dir(int(run_id), schema)
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        job_dir.mkdir(parents=True, exist_ok=True)

        job = AiBundleExportJob(
            job_id=str(uuid.uuid4()),
            run_id=int(run_id),
            export_schema_version=schema,
            status="pending",
            phase="queued",
            progress_pct=0.0,
            progress_message="In coda",
            job_dir=str(job_dir),
        )
        job.persist()
        _jobs[job.job_id] = job
        _key_to_job[key] = job.job_id

    executor.submit(_run_job, job.job_id)
    return job


def _set_progress(
    job: AiBundleExportJob,
    *,
    status: JobStatus | None = None,
    phase: str | None = None,
    progress_pct: float | None = None,
    message: str | None = None,
) -> None:
    with _lock:
        if status is not None:
            job.status = status
        if phase is not None:
            job.phase = phase
        if progress_pct is not None:
            job.progress_pct = max(0.0, min(100.0, float(progress_pct)))
        if message is not None:
            job.progress_message = message
        job.persist()


def _run_job(job_id: str) -> None:
    from app.services.cecchino_data_lab.run_v2.ai_bundle import write_ai_bundle_zip_to_path

    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "building"
        job.started_at = _utcnow_iso()
        job._started_monotonic = time.monotonic()
        job.retryable = False
        job.error_code = None
        job.error_message = None
        job.phase = "starting"
        job.progress_pct = 1.0
        job.progress_message = "Avvio export"
        job.persist()

    db = SessionLocal()
    try:

        def on_phase(phase: str, pct: float, message: str) -> None:
            _set_progress(
                job,
                status="building",
                phase=phase,
                progress_pct=pct,
                message=message,
            )

        zip_file = _zip_path(Path(job.job_dir))
        filename, size, counts = write_ai_bundle_zip_to_path(
            db,
            job.run_id,
            zip_file,
            work_dir=Path(job.job_dir) / "work",
            on_phase=on_phase,
        )
        with _lock:
            job.status = "ready"
            job.phase = "ready"
            job.progress_pct = 100.0
            job.progress_message = "Pacchetto pronto"
            job.filename = filename
            job.zip_bytes = int(size)
            job.export_counts = dict(counts or {})
            job.completed_at = _utcnow_iso()
            job.persist()
        logger.info(
            "run_v2 ai-bundle job ready run_id=%s job_id=%s bytes=%s",
            job.run_id,
            job.job_id,
            size,
        )
    except Exception as exc:
        logger.exception("run_v2 ai-bundle job failed run_id=%s", job.run_id)
        with _lock:
            job.status = "failed"
            job.phase = "failed"
            job.retryable = True
            job.error_code = "export_failed"
            job.error_message = str(exc)[:2000]
            job.completed_at = _utcnow_iso()
            job.persist()
    finally:
        db.close()


def resolve_download(
    run_id: int, *, schema_version: str = RUN_V2_EXPORT_SCHEMA_VERSION
) -> tuple[Path, str, int]:
    """Ritorna (zip_path, filename, size) se ready; altrimenti ValueError."""
    job = get_job_for_run(int(run_id), schema_version=schema_version)
    if job is None or job.status != "ready":
        raise ValueError("ai_bundle_not_ready")
    path = _zip_path(Path(job.job_dir))
    if not path.is_file():
        raise ValueError("ai_bundle_missing_file")
    filename = job.filename or path.name
    size = int(job.zip_bytes or path.stat().st_size)
    return path, filename, size
