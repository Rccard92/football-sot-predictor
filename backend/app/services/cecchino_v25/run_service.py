"""Avvio, ripresa e stato delle RUN V2.5 (stesso modello operativo della RUN V2)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import (
    RUN_V2_ACTIVE_STATUSES,
    RUN_V2_STATUS_PENDING,
    CecchinoRunV2Run,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2.preflight import run_v2_preflight
from app.services.cecchino_data_lab.run_v2.run_service import (
    RUN_V2_COMPLETED_STATUSES,
    RunV2LockNotAcquired,
    acquire_run_v2_lock,
    can_resume,
    is_run_stale,
    run_v2_to_dict,
)
from app.services.cecchino_v25 import scales
from app.services.cecchino_v25.constants import RUN_V25_CONFIRM_TOKEN, RUN_V25_VERSION

logger = logging.getLogger(__name__)

_threads: dict[int, threading.Thread] = {}
_lock = threading.Lock()


def list_runs_v25(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    runs = db.scalars(
        select(CecchinoRunV2Run)
        .where(CecchinoRunV2Run.run_version == RUN_V25_VERSION)
        .order_by(CecchinoRunV2Run.id.desc())
        .limit(int(limit))
    ).all()
    return [run_v2_to_dict(r) for r in runs]


def _require_v25(db: Session, run_id: int) -> CecchinoRunV2Run:
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None or run.run_version != RUN_V25_VERSION:
        raise CecchinoLabImportError("run_not_found", f"RUN V2.5 {run_id} inesistente", status_code=404)
    return run


def get_run_v25(db: Session, run_id: int) -> dict[str, Any]:
    return run_v2_to_dict(_require_v25(db, run_id))


def _worker(run_id: int) -> None:
    from app.services.cecchino_v25.executor import execute_run_v25

    try:
        with acquire_run_v2_lock(int(run_id)):
            execute_run_v25(int(run_id))
    except RunV2LockNotAcquired as exc:
        logger.warning("run_v25 lock occupato run_id=%s payload=%s", run_id, exc.payload)
    except Exception:
        logger.exception("run_v25 worker fallito run_id=%s", run_id)
    finally:
        with _lock:
            _threads.pop(int(run_id), None)


def _spawn(run_id: int) -> None:
    with _lock:
        existing = _threads.get(int(run_id))
        if existing is not None and existing.is_alive():
            return
        t = threading.Thread(target=_worker, args=(int(run_id),), name=f"cecchino-run-v25-{run_id}", daemon=True)
        _threads[int(run_id)] = t
        t.start()


def _guard_no_active_run(db: Session, *, exclude_id: int | None = None) -> None:
    """Una sola RUN (V2 o V2.5) alla volta: condividono tabelle e carico del backend."""
    q = select(CecchinoRunV2Run).where(CecchinoRunV2Run.status.in_(tuple(RUN_V2_ACTIVE_STATUSES)))
    if exclude_id is not None:
        q = q.where(CecchinoRunV2Run.id != int(exclude_id))
    active = db.scalars(q.order_by(CecchinoRunV2Run.id.desc())).first()
    if active is not None and not is_run_stale(active):
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste gia' una RUN in esecuzione (id={active.id}, {active.run_version})",
            status_code=409,
            details={"run_id": int(active.id), "status": active.status},
        )


def start_run_v25(db: Session, *, confirm: Any, season: Any, background: bool = True) -> dict[str, Any]:
    from app.services.cecchino_v25.executor import create_run_v25

    if confirm != RUN_V25_CONFIRM_TOKEN:
        raise CecchinoLabImportError("confirm_required", f"Token di conferma richiesto: {RUN_V25_CONFIRM_TOKEN}", status_code=400)
    season_label = str(season or "").strip()
    if not season_label:
        raise CecchinoLabImportError("season_required", "Parametro season obbligatorio (es. 2021/2022)", status_code=400)
    if not scales.scales_version():
        raise CecchinoLabImportError("scales_missing", "Scale V2.5 non ancora tarate", status_code=409)
    preflight = run_v2_preflight(db, season_label=season_label)
    if preflight.get("status") != "ready":
        raise CecchinoLabImportError(
            "season_unavailable", f"Stagione {season_label} non disponibile", status_code=400, details={"preflight": preflight}
        )
    _guard_no_active_run(db)
    run = create_run_v25(db, season_label=season_label)
    if background:
        _spawn(int(run.id))
    else:
        _worker(int(run.id))
        db.refresh(run)
    return run_v2_to_dict(run)


def resume_run_v25(db: Session, run_id: int, *, background: bool = True) -> dict[str, Any]:
    run = _require_v25(db, run_id)
    if str(run.status or "") in RUN_V2_COMPLETED_STATUSES:
        raise CecchinoLabImportError("run_already_completed", "RUN V2.5 gia' completata", status_code=400)
    if not can_resume(run):
        raise CecchinoLabImportError("run_still_active", f"La RUN V2.5 #{run.id} e' ancora in esecuzione", status_code=409)
    _guard_no_active_run(db, exclude_id=int(run.id))
    run.cancel_requested = False
    run.status = RUN_V2_STATUS_PENDING
    run.error_json = None
    run.completed_at = None
    db.commit()
    if background:
        _spawn(int(run.id))
    else:
        _worker(int(run.id))
    db.refresh(run)
    return run_v2_to_dict(run)
