"""Orchestrazione RUN V2: avvio in background, stato, resume, cancel.

Il worker gira in un thread daemon nel processo backend, mentre lo stato della
run e persistente sul DB. Dopo un restart/deploy/crash una run puo quindi
restare `pending`/`running` senza alcun worker vivo: quel caso e trattato come
`interrupted` (stato *effettivo*, mai scritto sul DB) e resta riprendibile dal
checkpoint gia persistito negli snapshot.

Nessuna logica predittiva qui: l'executor e il core Cecchino restano invariati.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Iterator

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import (
    RUN_V2_ACTIVE_STATUSES,
    RUN_V2_STATUS_CANCELLED,
    RUN_V2_STATUS_COMPLETED,
    RUN_V2_STATUS_COMPLETED_WITH_WARNINGS,
    RUN_V2_STATUS_FAILED,
    RUN_V2_STATUS_INTERRUPTED,
    RUN_V2_STATUS_PENDING,
    CecchinoRunV2Run,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2.constants import (
    RUN_V2_ADVISORY_LOCK_NAMESPACE,
    RUN_V2_CONFIRM_TOKEN,
    RUN_V2_STALE_HEARTBEAT_SECONDS,
)
from app.services.cecchino_data_lab.run_v2.executor import season_label_from_run
from app.services.cecchino_data_lab.run_v2.preflight import run_v2_preflight

logger = logging.getLogger(__name__)

_active_threads: dict[int, threading.Thread] = {}
_lock = threading.Lock()

_run_process_locks: dict[int, threading.Lock] = {}
_run_process_locks_guard = threading.Lock()

RUN_V2_COMPLETED_STATUSES = frozenset(
    {RUN_V2_STATUS_COMPLETED, RUN_V2_STATUS_COMPLETED_WITH_WARNINGS}
)
RUN_V2_RESUMABLE_STATUSES = frozenset({RUN_V2_STATUS_FAILED, RUN_V2_STATUS_CANCELLED})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Liveness worker / heartbeat
# ---------------------------------------------------------------------------


def is_worker_alive(run_id: int) -> bool:
    """True se un worker per questa run e vivo in *questo* processo."""
    with _lock:
        t = _active_threads.get(int(run_id))
        return bool(t is not None and t.is_alive())


def heartbeat_at(run: CecchinoRunV2Run) -> datetime | None:
    """Ultimo segno di vita della run.

    `updated_at` e aggiornato dal TimestampMixin a ogni flush di progresso
    dell'executor: e l'heartbeat naturale, senza colonne aggiuntive.
    """
    return _aware(run.updated_at) or _aware(run.started_at) or _aware(run.requested_at)


def heartbeat_age_seconds(run: CecchinoRunV2Run) -> float | None:
    ref = heartbeat_at(run)
    if ref is None:
        return None
    return (_utcnow() - ref).total_seconds()


def is_run_stale(run: CecchinoRunV2Run) -> bool:
    """True se la run risulta attiva sul DB ma nessun worker la sta portando avanti."""
    if str(run.status or "") not in RUN_V2_ACTIVE_STATUSES:
        return False
    if is_worker_alive(int(run.id)):
        return False
    age = heartbeat_age_seconds(run)
    if age is None:
        return True
    return age > RUN_V2_STALE_HEARTBEAT_SECONDS


def effective_status(run: CecchinoRunV2Run) -> str:
    """Stato mostrato all'operatore: `interrupted` non viene mai scritto sul DB."""
    if is_run_stale(run):
        return RUN_V2_STATUS_INTERRUPTED
    return str(run.status or "")


def can_resume(run: CecchinoRunV2Run) -> bool:
    if str(run.status or "") in RUN_V2_COMPLETED_STATUSES:
        return False
    if str(run.status or "") in RUN_V2_RESUMABLE_STATUSES:
        return True
    return is_run_stale(run)


def can_cancel(run: CecchinoRunV2Run) -> bool:
    return str(run.status or "") in RUN_V2_ACTIVE_STATUSES


# ---------------------------------------------------------------------------
# Advisory lock per run (nessuna dipendenza nuova: PG + fallback di processo)
# ---------------------------------------------------------------------------

_RUN_V2_PG_TRY_LOCK_SQL = "SELECT pg_try_advisory_lock(CAST(:lock_key AS bigint))"
_RUN_V2_PG_UNLOCK_SQL = "SELECT pg_advisory_unlock(CAST(:lock_key AS bigint))"


class RunV2LockNotAcquired(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__("run_v2_lock_not_acquired")


def build_run_v2_advisory_lock_key(run_id: int) -> int:
    """Chiave bigint con segno derivata da namespace + run_id, stabile fra processi."""
    ns = int(RUN_V2_ADVISORY_LOCK_NAMESPACE) & 0xFFFFFFFF
    rid = int(run_id) & 0xFFFFFFFF
    unsigned64 = (ns << 32) | rid
    if unsigned64 >= (1 << 63):
        return int(unsigned64 - (1 << 64))
    return int(unsigned64)


def _is_postgres(engine: Engine) -> bool:
    return (engine.dialect.name or "").lower() in {"postgresql", "postgres"}


@contextmanager
def acquire_run_v2_lock(
    run_id: int,
    *,
    engine: Engine | None = None,
) -> Iterator[dict[str, Any]]:
    """Lock di esclusivita per run: advisory PostgreSQL, fallback di processo altrove.

    Il lock PG e legato alla sessione: se il processo muore il server lo
    rilascia da solo, quindi dopo un crash la run torna riprendibile.
    """
    if engine is None:
        from app.core.database import engine as default_engine

        engine = default_engine

    rid = int(run_id)
    started = time.monotonic()
    if _is_postgres(engine):
        yield from _acquire_pg_lock(engine, rid, started)
    else:
        yield from _acquire_process_lock(rid, started)


def _acquire_pg_lock(
    engine: Engine, run_id: int, started: float
) -> Generator[dict[str, Any], None, None]:
    lock_key = build_run_v2_advisory_lock_key(run_id)
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        row = conn.execute(
            text(_RUN_V2_PG_TRY_LOCK_SQL), {"lock_key": int(lock_key)}
        ).scalar()
        payload = {
            "acquired": bool(row),
            "backend": "postgresql_advisory",
            "lock_namespace": RUN_V2_ADVISORY_LOCK_NAMESPACE,
            "lock_key": lock_key,
            "run_id": run_id,
            "waited_seconds": round(time.monotonic() - started, 3),
        }
        if not payload["acquired"]:
            raise RunV2LockNotAcquired(payload)
        try:
            yield payload
        finally:
            try:
                conn.execute(text(_RUN_V2_PG_UNLOCK_SQL), {"lock_key": int(lock_key)})
            except Exception:
                logger.exception("run_v2 unlock fallito run_id=%s", run_id)
    finally:
        try:
            conn.close()
        except Exception:
            logger.exception("run_v2 chiusura connessione lock fallita run_id=%s", run_id)


def _acquire_process_lock(
    run_id: int, started: float
) -> Generator[dict[str, Any], None, None]:
    lock_key = build_run_v2_advisory_lock_key(run_id)
    with _run_process_locks_guard:
        lock = _run_process_locks.get(run_id)
        if lock is None:
            lock = threading.Lock()
            _run_process_locks[run_id] = lock
    acquired = lock.acquire(blocking=False)
    payload = {
        "acquired": acquired,
        "backend": "process_threading",
        "lock_namespace": RUN_V2_ADVISORY_LOCK_NAMESPACE,
        "lock_key": lock_key,
        "run_id": run_id,
        "waited_seconds": round(time.monotonic() - started, 3),
    }
    if not acquired:
        raise RunV2LockNotAcquired(payload)
    try:
        yield payload
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Serializzazione
# ---------------------------------------------------------------------------


def run_v2_to_dict(run: CecchinoRunV2Run) -> dict[str, Any]:
    """Payload comune a list e detail (consultazione pubblica).

    Solo metadata/aggregati per la UI: stato, progress, coverage, summary,
    audit. Nessuna riga raw, CSV export o secret.
    `status` resta il valore sul DB; `effective_status` e la lettura operativa
    che distingue una run realmente in corso da una rimasta appesa.
    """
    stale = is_run_stale(run)
    return {
        "run_id": int(run.id),
        "run_version": run.run_version,
        "status": run.status,
        "effective_status": effective_status(run),
        "is_stale": stale,
        "worker_alive": is_worker_alive(int(run.id)),
        "can_resume": can_resume(run),
        "can_cancel": can_cancel(run),
        "heartbeat_at": heartbeat_at(run),
        "heartbeat_age_seconds": (
            round(age, 1) if (age := heartbeat_age_seconds(run)) is not None else None
        ),
        "stale_heartbeat_seconds": RUN_V2_STALE_HEARTBEAT_SECONDS,
        "run_scope": run.run_scope,
        "season_label": season_label_from_run(run),
        "max_matches": run.max_matches,
        "requested_at": run.requested_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "matches_total": run.matches_total,
        "matches_processed": run.matches_processed,
        "matches_error": run.matches_error,
        "market_rows_written": run.market_rows_written,
        "leakage_violations": run.leakage_violations,
        "progress_pct": run.progress_pct,
        "min_kickoff_at": run.min_kickoff_at,
        "max_kickoff_at": run.max_kickoff_at,
        "current_competition": run.current_competition,
        "last_processed_kickoff_at": run.last_processed_kickoff_at,
        "cancel_requested": bool(run.cancel_requested),
        "quote_policy": run.quote_policy_json,
        "module_policy": run.module_policy_json,
        "coverage": run.coverage_json,
        "summary": run.summary_json,
        "leakage_audit": run.leakage_audit_json,
        "warnings": run.warnings_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
        "source_git_commit_source": run.source_git_commit_source,
        "source_revision_status": run.source_revision_status,
    }


# ---------------------------------------------------------------------------
# Letture
# ---------------------------------------------------------------------------


def list_runs_v2(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    runs = list(
        db.scalars(
            select(CecchinoRunV2Run)
            .order_by(CecchinoRunV2Run.id.desc())
            .limit(int(limit))
        ).all()
    )
    return [run_v2_to_dict(r) for r in runs]


def _require_run(db: Session, run_id: int) -> CecchinoRunV2Run:
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise CecchinoLabImportError(
            "run_not_found", f"RUN V2 {run_id} inesistente", status_code=404
        )
    return run


def get_run_v2(db: Session, run_id: int) -> dict[str, Any]:
    return run_v2_to_dict(_require_run(db, run_id))


def find_active_run_v2(db: Session) -> CecchinoRunV2Run | None:
    return db.scalars(
        select(CecchinoRunV2Run)
        .where(CecchinoRunV2Run.status.in_(tuple(RUN_V2_ACTIVE_STATUSES)))
        .order_by(CecchinoRunV2Run.id.desc())
    ).first()


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _run_v2_worker(run_id: int) -> None:
    """Esegue la run tenendo il lock di esclusivita. L'executor resta invariato."""
    from app.services.cecchino_data_lab.run_v2.executor import execute_run_v2

    try:
        with acquire_run_v2_lock(int(run_id)):
            execute_run_v2(int(run_id))
    except RunV2LockNotAcquired as exc:
        # Un altro worker (stesso processo o altra replica) sta gia lavorando
        # questa run: uscire e la scelta corretta, niente doppia elaborazione.
        logger.warning(
            "run_v2 lock occupato run_id=%s payload=%s", run_id, exc.payload
        )
    except Exception:
        logger.exception("run_v2 worker fallito run_id=%s", run_id)
    finally:
        with _lock:
            _active_threads.pop(int(run_id), None)


def _spawn_worker(run_id: int) -> None:
    with _lock:
        existing = _active_threads.get(int(run_id))
        if existing is not None and existing.is_alive():
            return
        t = threading.Thread(
            target=_run_v2_worker,
            args=(int(run_id),),
            name=f"cecchino-run-v2-{run_id}",
            daemon=True,
        )
        _active_threads[int(run_id)] = t
        t.start()


# ---------------------------------------------------------------------------
# Comandi
# ---------------------------------------------------------------------------


def _guard_no_concurrent_run(db: Session) -> None:
    """Blocca un nuovo avvio solo se esiste davvero un'elaborazione in corso.

    Una run stale non deve bloccare per sempre: viene segnalata con un codice
    dedicato, cosi il chiamante puo riprenderla o annullarla.
    """
    active = find_active_run_v2(db)
    if active is None:
        return
    payload = run_v2_to_dict(active)
    if is_run_stale(active):
        raise CecchinoLabImportError(
            "stale_active_run",
            (
                f"La RUN V2 #{active.id} risulta attiva ma nessun worker la sta "
                "elaborando (probabile restart del backend). Riprendila dal "
                "checkpoint oppure annullala prima di avviarne una nuova."
            ),
            status_code=409,
            details={
                "run_id": int(active.id),
                "status": active.status,
                "effective_status": RUN_V2_STATUS_INTERRUPTED,
                "resumable": True,
                "matches_processed": int(active.matches_processed or 0),
                "matches_total": int(active.matches_total or 0),
                "heartbeat_age_seconds": payload["heartbeat_age_seconds"],
            },
        )
    raise CecchinoLabImportError(
        "duplicate_active_run",
        f"Esiste gia una RUN V2 in esecuzione (id={active.id})",
        status_code=409,
        details={"run_id": int(active.id), "status": active.status},
    )


def _normalize_season_label(season: Any) -> str:
    text = str(season or "").strip()
    if not text:
        raise CecchinoLabImportError(
            "season_required",
            "Parametro season obbligatorio (es. 2024/2025)",
            status_code=400,
        )
    return text


def start_run_v2(
    db: Session,
    *,
    confirm: Any = None,
    season: Any = None,
    season_label: Any = None,
    max_matches: int | None = None,
    pilot_strategy: str | None = None,
    eligible_per_competition: int | None = None,
    background: bool = True,
) -> dict[str, Any]:
    from app.services.cecchino_data_lab.run_v2.constants import (
        RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION,
        RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
        RUN_V2_SCOPE_BALANCED_PILOT,
        RUN_V2_SCOPE_FULL,
        RUN_V2_SCOPE_PILOT,
    )
    from app.services.cecchino_data_lab.run_v2.executor import create_run_v2

    if confirm != RUN_V2_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "confirm_required",
            f"Token di conferma richiesto: {RUN_V2_CONFIRM_TOKEN}",
            status_code=400,
        )

    # Accetta `season` (contratto UI) oppure `season_label` (alias V1).
    normalized_season = _normalize_season_label(
        season if season is not None and str(season).strip() else season_label
    )

    strategy = str(pilot_strategy or "").strip() or None
    epc: int | None = None
    if eligible_per_competition is not None:
        try:
            epc = int(eligible_per_competition)
        except (TypeError, ValueError) as exc:
            raise CecchinoLabImportError(
                "invalid_eligible_per_competition",
                "eligible_per_competition deve essere un intero",
                status_code=400,
            ) from exc
        if epc <= 0:
            raise CecchinoLabImportError(
                "invalid_eligible_per_competition",
                "eligible_per_competition deve essere positivo",
                status_code=400,
            )

    normalized_max: int | None = None
    if max_matches is not None:
        try:
            normalized_max = int(max_matches)
        except (TypeError, ValueError) as exc:
            raise CecchinoLabImportError(
                "invalid_max_matches", "max_matches deve essere un intero", status_code=400
            ) from exc
        if normalized_max <= 0:
            raise CecchinoLabImportError(
                "invalid_max_matches", "max_matches deve essere positivo", status_code=400
            )

    if strategy == RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP or (
        epc is not None and strategy is None and normalized_max is None
    ):
        # Pilot maturo bilanciato: 3 eligible_core/comp di default.
        strategy = RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP
        if epc is None:
            epc = RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION
        run_scope = RUN_V2_SCOPE_BALANCED_PILOT
        normalized_max = None
    elif normalized_max is not None:
        run_scope = RUN_V2_SCOPE_PILOT
    else:
        run_scope = RUN_V2_SCOPE_FULL

    preflight = run_v2_preflight(db, season_label=normalized_season)
    if preflight.get("status") != "ready":
        anomalies = preflight.get("blocking_anomalies") or []
        message = (
            anomalies[0].get("message")
            if anomalies and isinstance(anomalies[0], dict)
            else f"Stagione {normalized_season} non disponibile"
        )
        raise CecchinoLabImportError(
            "season_unavailable",
            str(message),
            status_code=400,
            details={"preflight": preflight},
        )

    _guard_no_concurrent_run(db)

    revision = _resolve_revision()
    run = create_run_v2(
        db,
        season_label=normalized_season,
        max_matches=normalized_max,
        source_git_commit=revision.get("source_git_commit"),
        run_scope=run_scope,
        pilot_strategy=strategy,
        eligible_per_competition=epc,
    )
    run.source_git_commit_source = revision.get("source_git_commit_source")
    run.source_revision_status = revision.get("source_revision_status")
    db.commit()
    db.refresh(run)

    if background:
        _spawn_worker(int(run.id))
    else:
        _run_v2_worker(int(run.id))
        db.refresh(run)

    return run_v2_to_dict(run)


def resume_run_v2(
    db: Session, run_id: int, *, background: bool = True
) -> dict[str, Any]:
    run = _require_run(db, run_id)

    if str(run.status or "") in RUN_V2_COMPLETED_STATUSES:
        raise CecchinoLabImportError(
            "run_already_completed", "RUN V2 gia completata", status_code=400
        )
    if not can_resume(run):
        raise CecchinoLabImportError(
            "run_still_active",
            f"La RUN V2 #{run.id} e ancora in esecuzione: attendere o annullarla",
            status_code=409,
            details={"run_id": int(run.id), "status": run.status},
        )

    other = db.scalars(
        select(CecchinoRunV2Run)
        .where(
            CecchinoRunV2Run.status.in_(tuple(RUN_V2_ACTIVE_STATUSES)),
            CecchinoRunV2Run.id != int(run.id),
        )
        .order_by(CecchinoRunV2Run.id.desc())
    ).first()
    if other is not None and not is_run_stale(other):
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Un'altra RUN V2 e in esecuzione (id={other.id})",
            status_code=409,
            details={"run_id": int(other.id), "status": other.status},
        )

    # Riparte dal checkpoint: gli snapshot gia scritti non vengono toccati e
    # l'executor salta da solo i match completati.
    run.cancel_requested = False
    run.status = RUN_V2_STATUS_PENDING
    run.error_json = None
    run.completed_at = None
    db.commit()
    db.refresh(run)

    if background:
        _spawn_worker(int(run.id))
    else:
        _run_v2_worker(int(run.id))
        db.refresh(run)

    return run_v2_to_dict(run)


def cancel_run_v2(db: Session, run_id: int) -> dict[str, Any]:
    run = _require_run(db, run_id)
    run.cancel_requested = True
    if str(run.status or "") in RUN_V2_ACTIVE_STATUSES:
        # Se il worker e vivo se ne accorge al prossimo check; se la run era
        # stale non c'e nessuno da attendere e lo stato e gia definitivo.
        run.status = RUN_V2_STATUS_CANCELLED
        run.completed_at = _utcnow()
    db.commit()
    db.refresh(run)
    return run_v2_to_dict(run)


def _resolve_revision() -> dict[str, Any]:
    try:
        from app.services.cecchino_data_lab.revision_resolve import (
            revision_as_source_fields,
        )

        return revision_as_source_fields()
    except Exception:  # noqa: BLE001 - la provenance non deve bloccare l'avvio
        logger.warning("run_v2: revisione sorgente non risolvibile", exc_info=True)
        return {}


__all__ = [
    "RUN_V2_STATUS_INTERRUPTED",
    "RunV2LockNotAcquired",
    "acquire_run_v2_lock",
    "can_cancel",
    "can_resume",
    "cancel_run_v2",
    "effective_status",
    "find_active_run_v2",
    "get_run_v2",
    "is_run_stale",
    "is_worker_alive",
    "list_runs_v2",
    "resume_run_v2",
    "run_v2_preflight",
    "run_v2_to_dict",
    "start_run_v2",
]
