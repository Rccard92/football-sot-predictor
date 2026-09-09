"""Recovery RUN V2 dopo restart/crash del backend.

Una run puo restare `pending`/`running` sul DB senza worker vivo. Deve
risultare `interrupted` (stato solo effettivo), restare riprendibile dal
checkpoint e non bloccare per sempre l'avvio di una nuova run.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from sqlalchemy import create_engine

from app.models.cecchino_run_v2 import (
    RUN_V2_STATUS_CANCELLED,
    RUN_V2_STATUS_COMPLETED,
    RUN_V2_STATUS_INTERRUPTED,
    RUN_V2_STATUS_PENDING,
    RUN_V2_STATUS_RUNNING,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2 import run_service
from app.services.cecchino_data_lab.run_v2.constants import (
    RUN_V2_CONFIRM_TOKEN,
    RUN_V2_STALE_HEARTBEAT_SECONDS,
)

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)


def _run(
    *,
    run_id: int = 1,
    status: str = RUN_V2_STATUS_RUNNING,
    heartbeat_age_seconds: float = 5.0,
    matches_processed: int = 12000,
    matches_total: int = 31000,
    cancel_requested: bool = False,
) -> SimpleNamespace:
    updated_at = datetime.now(timezone.utc) - timedelta(seconds=heartbeat_age_seconds)
    return SimpleNamespace(
        id=run_id,
        run_version="cecchino_run_v2",
        status=status,
        run_scope="full",
        max_matches=None,
        requested_at=NOW,
        started_at=NOW,
        completed_at=None,
        created_at=NOW,
        updated_at=updated_at,
        matches_total=matches_total,
        matches_processed=matches_processed,
        matches_error=0,
        market_rows_written=matches_processed * 17,
        leakage_violations=0,
        progress_pct=None,
        min_kickoff_at=None,
        max_kickoff_at=None,
        current_competition="E0",
        last_processed_kickoff_at=None,
        cancel_requested=cancel_requested,
        quote_policy_json=None,
        module_policy_json=None,
        coverage_json=None,
        summary_json=None,
        leakage_audit_json=None,
        warnings_json=None,
        error_json={"code": "boom"},
        source_git_commit=None,
        source_git_commit_source=None,
        source_revision_status=None,
    )


class FakeSession:
    """Sessione minimale: `get` per id, `scalars` con risultato preimpostato."""

    def __init__(self, *, by_id=None, scalar_first=None):
        self._by_id = by_id or {}
        self._scalar_first = scalar_first
        self.commits = 0

    def get(self, _model, run_id):
        return self._by_id.get(int(run_id))

    def scalars(self, _stmt):
        first = self._scalar_first
        return SimpleNamespace(first=lambda: first, all=lambda: [])

    def commit(self):
        self.commits += 1

    def refresh(self, _obj):
        return None


@pytest.fixture(autouse=True)
def _clean_thread_registry():
    with run_service._lock:
        run_service._active_threads.clear()
    yield
    with run_service._lock:
        run_service._active_threads.clear()


# ---------------------------------------------------------------------------
# Stato effettivo
# ---------------------------------------------------------------------------


def test_run_senza_worker_oltre_soglia_e_interrupted_ma_status_db_invariato():
    run = _run(heartbeat_age_seconds=RUN_V2_STALE_HEARTBEAT_SECONDS + 60)

    assert run_service.is_run_stale(run) is True
    assert run_service.effective_status(run) == RUN_V2_STATUS_INTERRUPTED
    assert run_service.can_resume(run) is True
    # Lo stato persistente non viene mai riscritto dalla sola lettura.
    assert run.status == RUN_V2_STATUS_RUNNING

    payload = run_service.run_v2_to_dict(run)
    assert payload["status"] == RUN_V2_STATUS_RUNNING
    assert payload["effective_status"] == RUN_V2_STATUS_INTERRUPTED
    assert payload["is_stale"] is True
    assert payload["worker_alive"] is False
    assert payload["can_resume"] is True
    assert payload["matches_processed"] == 12000


def test_run_con_heartbeat_fresco_non_e_stale():
    run = _run(heartbeat_age_seconds=5)

    assert run_service.is_run_stale(run) is False
    assert run_service.effective_status(run) == RUN_V2_STATUS_RUNNING
    assert run_service.can_resume(run) is False


def test_worker_locale_vivo_batte_heartbeat_vecchio():
    run = _run(run_id=7, heartbeat_age_seconds=RUN_V2_STALE_HEARTBEAT_SECONDS + 600)
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, daemon=True)
    t.start()
    with run_service._lock:
        run_service._active_threads[7] = t
    try:
        assert run_service.is_worker_alive(7) is True
        assert run_service.is_run_stale(run) is False
        assert run_service.effective_status(run) == RUN_V2_STATUS_RUNNING
    finally:
        stop.set()
        t.join(timeout=5)


def test_run_terminale_non_e_mai_stale():
    run = _run(
        status=RUN_V2_STATUS_COMPLETED,
        heartbeat_age_seconds=RUN_V2_STALE_HEARTBEAT_SECONDS * 10,
    )

    assert run_service.is_run_stale(run) is False
    assert run_service.effective_status(run) == RUN_V2_STATUS_COMPLETED
    assert run_service.can_resume(run) is False


# ---------------------------------------------------------------------------
# Guardia di avvio
# ---------------------------------------------------------------------------


def test_start_con_run_stale_segnala_stale_active_run_e_non_duplicate(monkeypatch):
    stale = _run(run_id=41, heartbeat_age_seconds=RUN_V2_STALE_HEARTBEAT_SECONDS + 60)
    db = FakeSession(by_id={41: stale}, scalar_first=stale)
    monkeypatch.setattr(run_service, "_spawn_worker", lambda _rid: None)

    with pytest.raises(CecchinoLabImportError) as exc:
        run_service.start_run_v2(db, confirm=RUN_V2_CONFIRM_TOKEN)

    assert exc.value.code == "stale_active_run"
    assert exc.value.status_code == 409
    assert exc.value.details["run_id"] == 41
    assert exc.value.details["resumable"] is True
    assert exc.value.details["effective_status"] == RUN_V2_STATUS_INTERRUPTED
    assert exc.value.details["matches_processed"] == 12000


def test_start_con_run_realmente_attiva_resta_duplicate_active_run(monkeypatch):
    live = _run(run_id=42, heartbeat_age_seconds=3)
    db = FakeSession(by_id={42: live}, scalar_first=live)
    monkeypatch.setattr(run_service, "_spawn_worker", lambda _rid: None)

    with pytest.raises(CecchinoLabImportError) as exc:
        run_service.start_run_v2(db, confirm=RUN_V2_CONFIRM_TOKEN)

    assert exc.value.code == "duplicate_active_run"
    assert exc.value.status_code == 409


def test_start_senza_token_rifiutato():
    db = FakeSession()
    with pytest.raises(CecchinoLabImportError) as exc:
        run_service.start_run_v2(db, confirm="nope")
    assert exc.value.code == "confirm_required"
    assert exc.value.status_code == 400


def test_start_torna_subito_run_id_e_stato(monkeypatch):
    created = _run(run_id=99, status=RUN_V2_STATUS_PENDING)
    spawned: list[int] = []
    monkeypatch.setattr(run_service, "_spawn_worker", lambda rid: spawned.append(rid))
    monkeypatch.setattr(
        "app.services.cecchino_data_lab.run_v2.executor.create_run_v2",
        lambda _db, **_kw: created,
    )
    db = FakeSession(by_id={99: created}, scalar_first=None)

    result = run_service.start_run_v2(db, confirm=RUN_V2_CONFIRM_TOKEN)

    assert result["run_id"] == 99
    assert result["status"] == RUN_V2_STATUS_PENDING
    assert spawned == [99]


# ---------------------------------------------------------------------------
# Resume dal checkpoint
# ---------------------------------------------------------------------------


def test_resume_di_run_stale_riparte_dal_checkpoint(monkeypatch):
    stale = _run(
        run_id=55,
        heartbeat_age_seconds=RUN_V2_STALE_HEARTBEAT_SECONDS + 120,
        cancel_requested=True,
    )
    db = FakeSession(by_id={55: stale}, scalar_first=None)
    spawned: list[int] = []
    monkeypatch.setattr(run_service, "_spawn_worker", lambda rid: spawned.append(rid))

    result = run_service.resume_run_v2(db, 55)

    assert spawned == [55]
    assert stale.status == RUN_V2_STATUS_PENDING
    assert stale.cancel_requested is False
    assert stale.error_json is None
    # Il progresso persistito non viene azzerato: l'executor salta i match fatti.
    assert stale.matches_processed == 12000
    assert result["run_id"] == 55


def test_resume_di_run_cancellata_e_ammesso(monkeypatch):
    cancelled = _run(run_id=56, status=RUN_V2_STATUS_CANCELLED, cancel_requested=True)
    db = FakeSession(by_id={56: cancelled}, scalar_first=None)
    monkeypatch.setattr(run_service, "_spawn_worker", lambda _rid: None)

    run_service.resume_run_v2(db, 56)

    assert cancelled.status == RUN_V2_STATUS_PENDING
    assert cancelled.cancel_requested is False


def test_resume_di_run_viva_rifiutato(monkeypatch):
    live = _run(run_id=57, heartbeat_age_seconds=2)
    db = FakeSession(by_id={57: live}, scalar_first=None)
    monkeypatch.setattr(run_service, "_spawn_worker", lambda _rid: None)

    with pytest.raises(CecchinoLabImportError) as exc:
        run_service.resume_run_v2(db, 57)

    assert exc.value.code == "run_still_active"
    assert exc.value.status_code == 409


def test_resume_di_run_completata_rifiutato():
    done = _run(run_id=58, status=RUN_V2_STATUS_COMPLETED)
    db = FakeSession(by_id={58: done}, scalar_first=None)

    with pytest.raises(CecchinoLabImportError) as exc:
        run_service.resume_run_v2(db, 58)

    assert exc.value.code == "run_already_completed"
    assert exc.value.status_code == 400


def test_cancel_di_run_stale_e_immediato():
    stale = _run(run_id=59, heartbeat_age_seconds=RUN_V2_STALE_HEARTBEAT_SECONDS + 60)
    db = FakeSession(by_id={59: stale}, scalar_first=None)

    result = run_service.cancel_run_v2(db, 59)

    assert stale.status == RUN_V2_STATUS_CANCELLED
    assert stale.cancel_requested is True
    assert result["can_resume"] is True


# ---------------------------------------------------------------------------
# Esclusivita del worker
# ---------------------------------------------------------------------------


def test_lock_impedisce_due_worker_sulla_stessa_run():
    engine = create_engine("sqlite://")

    with run_service.acquire_run_v2_lock(1234, engine=engine) as first:
        assert first["acquired"] is True
        with pytest.raises(run_service.RunV2LockNotAcquired):
            with run_service.acquire_run_v2_lock(1234, engine=engine):
                pytest.fail("il secondo worker non deve ottenere il lock")

    # Rilasciato: la run torna riprendibile.
    with run_service.acquire_run_v2_lock(1234, engine=engine) as again:
        assert again["acquired"] is True


def test_lock_non_blocca_run_diverse():
    engine = create_engine("sqlite://")
    with run_service.acquire_run_v2_lock(1, engine=engine):
        with run_service.acquire_run_v2_lock(2, engine=engine) as other:
            assert other["acquired"] is True


def test_worker_esce_senza_eseguire_se_il_lock_e_occupato(monkeypatch):
    chiamate: list[int] = []
    monkeypatch.setattr(
        "app.services.cecchino_data_lab.run_v2.executor.execute_run_v2",
        lambda rid: chiamate.append(rid),
    )

    @contextmanager
    def _busy(_run_id, **_kwargs):
        raise run_service.RunV2LockNotAcquired({"acquired": False, "run_id": _run_id})
        yield  # pragma: no cover

    monkeypatch.setattr(run_service, "acquire_run_v2_lock", _busy)

    run_service._run_v2_worker(77)

    assert chiamate == []


def test_worker_esegue_e_ripulisce_il_registro(monkeypatch):
    chiamate: list[int] = []
    monkeypatch.setattr(
        "app.services.cecchino_data_lab.run_v2.executor.execute_run_v2",
        lambda rid: chiamate.append(rid),
    )

    @contextmanager
    def _free(_run_id, **_kwargs):
        yield {"acquired": True}

    monkeypatch.setattr(run_service, "acquire_run_v2_lock", _free)
    with run_service._lock:
        run_service._active_threads[78] = threading.current_thread()

    run_service._run_v2_worker(78)

    assert chiamate == [78]
    assert run_service.is_worker_alive(78) is False


def test_chiave_advisory_lock_stabile_e_nel_range_bigint():
    key = run_service.build_run_v2_advisory_lock_key(31000)
    assert key == run_service.build_run_v2_advisory_lock_key(31000)
    assert -(2**63) <= key <= 2**63 - 1
    assert key != run_service.build_run_v2_advisory_lock_key(31001)
