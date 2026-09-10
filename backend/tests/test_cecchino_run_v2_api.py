"""API RUN V2: avvio non bloccante, stato, resume, cancel, export manifest."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.admin_session import AdminSession, require_admin_session
from app.core.database import get_db
from app.models.cecchino_run_v2 import (
    RUN_V2_STATUS_COMPLETED,
    RUN_V2_STATUS_PENDING,
    RUN_V2_STATUS_RUNNING,
)
from app.routes import cecchino_run_v2 as routes_v2
from app.services.cecchino_data_lab.run_v2 import run_service
from app.services.cecchino_data_lab.run_v2.constants import RUN_V2_CONFIRM_TOKEN

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)


def _run(*, run_id: int = 1, status: str = RUN_V2_STATUS_RUNNING, heartbeat_age: float = 3.0):
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
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=heartbeat_age),
        matches_total=31000,
        matches_processed=1500,
        matches_error=0,
        market_rows_written=25500,
        leakage_violations=0,
        progress_pct=None,
        min_kickoff_at=None,
        max_kickoff_at=None,
        current_competition="E0",
        last_processed_kickoff_at=None,
        cancel_requested=False,
        quote_policy_json={"quote_policy_version": "bet365_dual_track_v2"},
        module_policy_json={"season_label": "2024/2025", "season_scope": "2024/2025"},
        coverage_json=None,
        summary_json=None,
        leakage_audit_json={"leakage_ok": True},
        warnings_json=None,
        error_json=None,
        source_git_commit="abc123",
        source_git_commit_source="env",
        source_revision_status="resolved",
    )


class FakeSession:
    def __init__(self, *, by_id=None, scalar_first=None):
        self._by_id = by_id or {}
        self._scalar_first = scalar_first

    def get(self, _model, run_id):
        return self._by_id.get(int(run_id))

    def scalars(self, _stmt):
        first = self._scalar_first
        items = list(self._by_id.values())
        return SimpleNamespace(first=lambda: first, all=lambda: items)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def _client(db: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(routes_v2.router, prefix="/api")
    app.include_router(routes_v2.admin_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    # Sessione admin data per valida: qui si verifica il contratto HTTP della
    # RUN V2, l'autorizzazione ha i suoi test in test_admin_session_auth.py.
    app.dependency_overrides[require_admin_session] = lambda: AdminSession(
        expires_at=int(NOW.timestamp()) + 3600
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    """Nessun thread reale: i test verificano il contratto HTTP, non l'executor."""
    spawned: list[int] = []
    monkeypatch.setattr(run_service, "_spawn_worker", lambda rid: spawned.append(rid))
    monkeypatch.setattr(
        run_service,
        "run_v2_preflight",
        lambda _db, *, season_label: {
            "season_label": season_label,
            "status": "ready",
            "matches_total": 100,
            "competitions_count": 1,
            "competitions": ["E0"],
            "datasets_count": 1,
            "date_range": {"start": None, "end": None},
            "blocking_anomalies": [],
            "warnings": [],
        },
    )
    with run_service._lock:
        run_service._active_threads.clear()
    yield spawned
    with run_service._lock:
        run_service._active_threads.clear()


def test_start_richiede_token_di_conferma():
    client = _client(FakeSession())
    res = client.post("/api/admin/cecchino-run-v2", json={"season": "2024/2025"})

    assert res.status_code == 400
    body = res.json()
    assert body["error"] == "confirm_required"


def test_start_richiede_stagione(_no_worker):
    client = _client(FakeSession())
    res = client.post(
        "/api/admin/cecchino-run-v2", json={"confirm": RUN_V2_CONFIRM_TOKEN}
    )
    assert res.status_code == 400
    assert res.json()["error"] == "season_required"


def test_start_risponde_202_senza_attendere_la_run(monkeypatch, _no_worker):
    created = _run(run_id=12, status=RUN_V2_STATUS_PENDING)
    monkeypatch.setattr(
        "app.services.cecchino_data_lab.run_v2.executor.create_run_v2",
        lambda _db, **_kw: created,
    )
    client = _client(FakeSession(by_id={12: created}))

    res = client.post(
        "/api/admin/cecchino-run-v2",
        json={"confirm": RUN_V2_CONFIRM_TOKEN, "season": "2024/2025"},
    )

    assert res.status_code == 202
    body = res.json()
    assert body["run_id"] == 12
    assert body["status"] == RUN_V2_STATUS_PENDING
    assert body["season_label"] == "2024/2025"
    assert _no_worker == [12]


def test_start_bloccato_se_una_run_e_gia_in_esecuzione(_no_worker):
    live = _run(run_id=13)
    client = _client(FakeSession(by_id={13: live}, scalar_first=live))

    res = client.post(
        "/api/admin/cecchino-run-v2",
        json={"confirm": RUN_V2_CONFIRM_TOKEN, "season": "2024/2025"},
    )

    assert res.status_code == 409
    assert res.json()["error"] == "duplicate_active_run"


def test_lista_e_dettaglio_espongono_stato_effettivo():
    run = _run(run_id=14)
    client = _client(FakeSession(by_id={14: run}))

    listed = client.get("/api/cecchino-run-v2")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["run_id"] == 14
    assert item["effective_status"] == RUN_V2_STATUS_RUNNING

    detail = client.get("/api/cecchino-run-v2/14")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == RUN_V2_STATUS_RUNNING
    assert body["is_stale"] is False
    assert body["matches_processed"] == 1500
    assert body["leakage_violations"] == 0
    assert body["source_git_commit"] == "abc123"


def test_dettaglio_run_inesistente_404():
    client = _client(FakeSession())
    assert client.get("/api/cecchino-run-v2/999").status_code == 404


def test_cancel_marca_la_run_e_torna_200():
    run = _run(run_id=15)
    client = _client(FakeSession(by_id={15: run}))

    res = client.post("/api/admin/cecchino-run-v2/15/cancel")

    assert res.status_code == 200
    assert run.cancel_requested is True


def test_resume_su_run_completata_rifiutato():
    done = _run(run_id=16, status=RUN_V2_STATUS_COMPLETED)
    client = _client(FakeSession(by_id={16: done}))

    res = client.post("/api/admin/cecchino-run-v2/16/resume")

    assert res.status_code == 400
    assert res.json()["error"] == "run_already_completed"


def test_export_rifiuta_file_fuori_contratto():
    run = _run(run_id=17, status=RUN_V2_STATUS_COMPLETED)
    client = _client(FakeSession(by_id={17: run}))

    res = client.get("/api/cecchino-run-v2/17/export", params={"file": "segreti.csv"})

    assert res.status_code == 400


def test_export_espone_i_cinque_artefatti(monkeypatch):
    run = _run(run_id=18, status=RUN_V2_STATUS_COMPLETED)
    monkeypatch.setattr(
        routes_v2,
        "build_export_bundle",
        lambda _db, *, run_id, output_dir: {
            "run_id": run_id,
            "run_version": "cecchino_run_v2",
            "output_dir": str(output_dir),
            "files": {
                "FULL.csv": str(output_dir / "FULL.csv"),
                "core_markets_long.csv": str(output_dir / "core_markets_long.csv"),
                "SOURCE_RAW.csv": str(output_dir / "SOURCE_RAW.csv"),
                "DATA_DICTIONARY.json": str(output_dir / "DATA_DICTIONARY.json"),
                "run_summary.json": str(output_dir / "run_summary.json"),
            },
            "counts": {"full_rows": 1500},
        },
    )
    client = _client(FakeSession(by_id={18: run}))

    res = client.get("/api/cecchino-run-v2/18/export/manifest")

    assert res.status_code == 200
    assert set(res.json()["files"]) == {
        "FULL.csv",
        "core_markets_long.csv",
        "SOURCE_RAW.csv",
        "DATA_DICTIONARY.json",
        "run_summary.json",
    }


def test_ai_bundle_richiede_sessione_admin():
    """Senza sessione admin: l'endpoint AI bundle e bloccato (401/503 fail-closed)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    run = _run(run_id=19, status=RUN_V2_STATUS_COMPLETED)
    db = FakeSession(by_id={19: run})
    app = FastAPI()
    app.include_router(routes_v2.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    res = client.get("/api/cecchino-run-v2/19/export/ai-bundle")
    assert res.status_code in (401, 503)
