"""Avvio dei job V4 dalle rotte admin: un thread per job, una sola istanza per nome, traccia in cecchino_v4_jobs.

Nomi ammessi:
- pipeline live (API-Football): fixtures, post_match, lineups, injuries, standings, odds_snapshot, odds_closing,
  coverage_scan, backfill;
- calcolo: predict (previsioni + ragionamenti + shortlist provvisoria), shortlist (alias di predict senza
  ricalcolo motori), settle (regolamento voci con partita finita), daily (fixtures -> odds_snapshot -> predict -> settle);
- esami storici: exam_E1, exam_E2, exam_E4 (processo separato, scrivono docs/v4/esami/).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_v4 import CecchinoV4Job
from app.services.cecchino_v4.pipeline.day import build_days, settle_finished
from app.services.cecchino_v4.selection.shortlist import seal_shortlist, shortlist_payload

logger = logging.getLogger(__name__)

LIVE_JOBS = ("fixtures", "post_match", "lineups", "injuries", "standings", "odds_snapshot", "odds_closing", "coverage_scan", "backfill")
COMPUTE_JOBS = ("predict", "shortlist", "settle", "daily")
EXAM_JOBS = ("exam_E1", "exam_E2", "exam_E4")
EXAM_MODULES = {
    "exam_E1": "app.services.cecchino_v4.exams.e1",
    "exam_E2": "app.services.cecchino_v4.exams.e2",
    "exam_E4": "app.services.cecchino_v4.exams.e4",
}
BACKEND_DIR = Path(__file__).resolve().parents[4]

_lock = threading.Lock()
_running: dict[str, threading.Thread] = {}


class UnknownJobName(Exception):
    pass


class JobBusy(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session() -> Session:
    from app.core.database import SessionLocal

    return SessionLocal()


def _parse_day(params: dict[str, Any]) -> list[date] | None:
    raw = params.get("date")
    if not raw:
        return None
    return [date.fromisoformat(str(raw))]


def _tracked(db: Session, name: str, params: dict[str, Any]) -> CecchinoV4Job:
    job = CecchinoV4Job(
        id=str(uuid.uuid4()),
        name=name,
        status="running",
        params_json=params or None,
        progress_pct=0.0,
        step="avvio",
        api_calls=0,
        heartbeat_at=_now(),
        created_at=_now(),
    )
    db.add(job)
    db.commit()
    return job


def _finish(db: Session, job: CecchinoV4Job, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    job.status = "failed" if error else "done"
    job.error_message = error
    job.result_json = result
    job.progress_pct = 100.0 if not error else job.progress_pct
    job.step = "completato" if not error else "errore"
    job.heartbeat_at = _now()
    job.finished_at = _now()
    db.add(job)
    db.commit()


def run_compute(db: Session, name: str, params: dict[str, Any]) -> dict[str, Any]:
    days = _parse_day(params)
    if name == "predict":
        return {"report": str(build_days(db, days=days))}
    if name == "shortlist":
        return {"report": str(build_days(db, days=days, recompute_predictions=False))}
    if name == "settle":
        return {"settled": settle_finished(db)}
    if name == "daily":
        out: dict[str, Any] = {}
        from app.services.cecchino_v4.live import jobs as live_jobs
        from app.services.cecchino_v4.live.client import V4ApiClient

        client = V4ApiClient(db=db)
        for step in ("fixtures", "odds_snapshot"):
            row = live_jobs.run_job(db, step, client=client, params=params)
            out[step] = {"status": row.status, "error": row.error_message, "api_calls": row.api_calls}
        out["predict"] = str(build_days(db, days=days))
        out["settled"] = settle_finished(db)
        return out
    raise UnknownJobName(name)


def _run_in_thread(name: str, params: dict[str, Any]) -> str:
    db = _session()
    try:
        if name in LIVE_JOBS:
            from app.services.cecchino_v4.live import jobs as live_jobs
            from app.services.cecchino_v4.live.client import V4ApiClient

            if live_jobs.running_job(db, name) is not None:
                raise JobBusy(f"job '{name}' gia' in esecuzione")
            job_id_holder: dict[str, str] = {}

            def target() -> None:
                s = _session()
                try:
                    row = live_jobs.run_job(s, name, client=V4ApiClient(db=s), params=params)
                    job_id_holder["id"] = row.id
                except Exception:  # noqa: BLE001
                    logger.exception("job live V4 %s fallito", name)
                finally:
                    s.close()
                    with _lock:
                        _running.pop(name, None)

            # l'id viene creato dentro run_job: ne anticipiamo uno visibile nella risposta
            job_id = f"{name}:{uuid.uuid4()}"
            _start(name, target)
            return job_id

        job = _tracked(db, name, params)
        job_id = job.id

        def target_compute() -> None:
            s = _session()
            try:
                j = s.get(CecchinoV4Job, job_id)
                try:
                    if name in COMPUTE_JOBS:
                        result = run_compute(s, name, params)
                    else:
                        result = _run_exam(name)
                    _finish(s, j, result=result)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("job V4 %s fallito", name)
                    s.rollback()
                    _finish(s, j, error=f"{exc.__class__.__name__}: {exc}"[:2000])
            finally:
                s.close()
                with _lock:
                    _running.pop(name, None)

        _start(name, target_compute)
        return job_id
    finally:
        db.close()


def _start(name: str, target) -> None:
    thread = threading.Thread(target=target, name=f"v4-{name}", daemon=True)
    with _lock:
        _running[name] = thread
    thread.start()


def _run_exam(name: str) -> dict[str, Any]:
    module = EXAM_MODULES[name]
    proc = subprocess.run(
        [sys.executable, "-m", module],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=3 * 3600,
    )
    tail = (proc.stdout or "")[-4000:]
    if proc.returncode != 0:
        raise RuntimeError(f"esame {name} terminato con codice {proc.returncode}: {(proc.stderr or '')[-1500:]}")
    return {"module": module, "stdout_tail": tail}


def start(name: str, params: dict[str, Any] | None = None) -> str:
    """Avvia il job in sottofondo e ritorna un identificativo. JobBusy se lo stesso nome e' gia' attivo."""
    params = dict(params or {})
    if name not in LIVE_JOBS + COMPUTE_JOBS + EXAM_JOBS:
        raise UnknownJobName(f"job sconosciuto: {name}")
    with _lock:
        t = _running.get(name)
        if t is not None and t.is_alive():
            raise JobBusy(f"job '{name}' gia' in esecuzione")
    return _run_in_thread(name, params)


def seal(db: Session, day: date) -> dict[str, Any]:
    seal_shortlist(db, day)
    db.commit()
    return shortlist_payload(db, day) or {}


def running_names() -> list[str]:
    with _lock:
        return [n for n, t in _running.items() if t.is_alive()]


def recent(db: Session, limit: int = 30) -> list[CecchinoV4Job]:
    return list(db.execute(select(CecchinoV4Job).order_by(CecchinoV4Job.created_at.desc()).limit(limit)).scalars())
