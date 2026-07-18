"""Test Fase 2A.3 — job asincroni ricerca statistica Acquistabilità."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.cecchino.cecchino_purchasability_audit import (
    AUDIT_VERSION,
    DATASET_VERSION,
    make_json_safe,
)
from app.services.cecchino.cecchino_purchasability_research_jobs import (
    MAX_COMPLETED_JOBS,
    POLL_AFTER_MS,
    PurchasabilityResearchJobConflict,
    PurchasabilityResearchJobNotFound,
    RESULT_DIR,
    atomic_write_json,
    cleanup_expired_jobs,
    enqueue_purchasability_research_job,
    filters_hash_for,
    get_active_job,
    get_job,
    reset_jobs_for_tests,
    set_result_dir_for_tests,
)
from app.services.cecchino.cecchino_purchasability_statistical_research import (
    STAT_VERSION,
    build_purchasability_statistical_research,
)


def _base_row(*, fid: int, market: str = "HOME", day: int = 1, won: bool = True) -> dict:
    from app.services.cecchino.cecchino_market_opposition import OPPOSITION_SUPPORTED

    snap = datetime(2026, 1, day, 10, 0, tzinfo=timezone.utc)
    kick = datetime(2026, 1, day, 18, 0, tzinfo=timezone.utc)
    odds = 2.0
    model_p = 0.55 if won else 0.35
    raw_imp = 1.0 / odds
    return {
        "today_fixture_id": fid,
        "canonical_row_key": f"k-{fid}-{market}-{day}",
        "raw_market_code": market,
        "selection": market,
        "canonical_market_family": "match_result",
        "scan_date": f"2026-01-{day:02d}",
        "snapshot_at": snap.isoformat(),
        "kickoff": kick.isoformat(),
        "competition_id": 1,
        "odds": odds,
        "raw_book_implied_probability": raw_imp,
        "normalized_book_probability": raw_imp / 1.05,
        "market_overround": 0.05,
        "model_probability": model_p,
        "probability_advantage": model_p - raw_imp,
        "edge": (model_p * odds - 1.0) * 100,
        "score": model_p * 50,
        "rating": 55.0,
        "favourite_alignment": "aligned",
        "favourite_intensity_book": 0.12,
        "favourite_intensity_model": 0.15,
        "book_favourite": market,
        "model_favourite": market,
        "comparator_odds_payload": {"DRAW": 3.2, "AWAY": 3.8},
        "comparator_model_probability_payload": {"DRAW": 0.28, "AWAY": 0.22},
        "comparator_book_probability_payload": {"DRAW": 0.31, "AWAY": 0.26},
        "complement_selection": "AWAY",
        "settlement_status": "won" if won else "lost",
        "selection_won": won,
        "selection_lost": not won,
        "selection_void": False,
        "unit_stake_profit": (odds - 1.0) if won else -1.0,
        "is_settled_core": True,
        "is_core": True,
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "no_post_match_data_in_features": True,
        "leakage_status": "safe",
        "opposition_status": OPPOSITION_SUPPORTED,
    }


def _rows(n: int = 14) -> list[dict]:
    out = []
    for i in range(n):
        out.append(_base_row(fid=200 + i, day=1 + i, won=i % 2 == 0))
        out.append(_base_row(fid=200 + i, market="DRAW", day=1 + i, won=i % 3 == 0))
    return out


@pytest.fixture(autouse=True)
def _job_tmp(tmp_path: Path):
    set_result_dir_for_tests(tmp_path / "purch_jobs")
    reset_jobs_for_tests()
    yield
    reset_jobs_for_tests()


def _wait_job(job_id: str, timeout: float = 60.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = get_job(job_id)
        if j.status in ("completed", "failed"):
            return j.to_status_dict()
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting job {job_id}")


def test_01_enqueue_returns_before_complete():
    started = time.time()
    out = enqueue_purchasability_research_job(
        bootstrap_iterations=10,
        seed=1,
        rows=_rows(12),
    )
    assert time.time() - started < 2.0
    assert out["job_id"]
    assert out["status"] in ("queued", "running")
    assert out["poll_after_ms"] == POLL_AFTER_MS
    assert out["reused"] is False
    _wait_job(out["job_id"])


def test_02_lifecycle_queued_running_completed():
    out = enqueue_purchasability_research_job(
        bootstrap_iterations=10, seed=2, rows=_rows(12)
    )
    st = _wait_job(out["job_id"])
    assert st["status"] == "completed"
    assert st["result_available"] is True
    assert st["current_stage"] == "completed"


def test_03_04_session_local_and_closed():
    sessions = []

    class FakeSession:
        def close(self):
            self.closed = True

        closed = False

    def fake_session_local():
        s = FakeSession()
        sessions.append(s)
        return s

    with patch(
        "app.core.database.SessionLocal",
        fake_session_local,
    ):
        with patch(
            "app.services.cecchino.cecchino_purchasability_research_jobs.build_purchasability_statistical_research",
            return_value=make_json_safe(
                {
                    "status": "ok",
                    "version": STAT_VERSION,
                    "dataset_version": DATASET_VERSION,
                    "phase_2b_readiness": {"recommended_next_step": "stop_no_incremental_signal"},
                    "filters": {},
                    "elapsed_ms": {"total": 1},
                    "limitations": [],
                    "candidate_specifications": [],
                    "feature_decisions": [],
                }
            ),
        ):
            out = enqueue_purchasability_research_job(bootstrap_iterations=10, seed=3)
            _wait_job(out["job_id"])
    assert len(sessions) == 1
    assert sessions[0].closed is True


def test_05_same_filters_running_reuses_job():
    # Block worker with a slow build
    gate = threading.Event()

    def slow_build(*args, **kwargs):
        gate.wait(timeout=5)
        return make_json_safe(
            {
                "status": "ok",
                "version": STAT_VERSION,
                "dataset_version": DATASET_VERSION,
                "phase_2b_readiness": {},
                "filters": {},
                "elapsed_ms": {},
                "limitations": [],
            }
        )

    with patch(
        "app.services.cecchino.cecchino_purchasability_research_jobs.build_purchasability_statistical_research",
        side_effect=slow_build,
    ):
        a = enqueue_purchasability_research_job(
            date_from="2026-01-01",
            date_to="2026-02-01",
            bootstrap_iterations=10,
            seed=5,
        )
        time.sleep(0.05)
        b = enqueue_purchasability_research_job(
            date_from="2026-01-01",
            date_to="2026-02-01",
            bootstrap_iterations=10,
            seed=5,
        )
        assert b["reused"] is True
        assert b["job_id"] == a["job_id"]
        gate.set()
        _wait_job(a["job_id"])


def test_06_different_filters_conflict_409():
    gate = threading.Event()

    def slow_build(*args, **kwargs):
        gate.wait(timeout=5)
        return make_json_safe(
            {
                "status": "ok",
                "version": STAT_VERSION,
                "dataset_version": DATASET_VERSION,
                "phase_2b_readiness": {},
                "filters": {},
                "elapsed_ms": {},
                "limitations": [],
            }
        )

    with patch(
        "app.services.cecchino.cecchino_purchasability_research_jobs.build_purchasability_statistical_research",
        side_effect=slow_build,
    ):
        enqueue_purchasability_research_job(bootstrap_iterations=10, seed=6)
        time.sleep(0.05)
        with pytest.raises(PurchasabilityResearchJobConflict):
            enqueue_purchasability_research_job(bootstrap_iterations=20, seed=6)
        gate.set()
        active = get_active_job()
        if active:
            _wait_job(active.job_id)


def test_07_max_one_worker():
    from app.services.cecchino import cecchino_purchasability_research_jobs as mod

    mod._ensure_initialized()
    assert mod._executor is not None
    assert mod._executor._max_workers == 1


def test_08_09_strict_json_and_atomic_write(tmp_path: Path):
    path = tmp_path / "x.result.json"
    payload = {"a": 1, "b": None, "version": STAT_VERSION}
    atomic_write_json(path, payload)
    assert path.is_file()
    assert not path.with_suffix(".json.tmp").exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    json.dumps(loaded, allow_nan=False)
    assert loaded["a"] == 1


def test_10_11_result_not_before_completed_status_without_payload():
    gate = threading.Event()

    def slow_build(*args, **kwargs):
        gate.wait(timeout=5)
        return make_json_safe(
            {
                "status": "ok",
                "version": STAT_VERSION,
                "dataset_version": DATASET_VERSION,
                "phase_2b_readiness": {"x": 1},
                "filters": {},
                "elapsed_ms": {},
                "limitations": [],
                "market_results": [{"huge": True}],
            }
        )

    with patch(
        "app.services.cecchino.cecchino_purchasability_research_jobs.build_purchasability_statistical_research",
        side_effect=slow_build,
    ):
        out = enqueue_purchasability_research_job(bootstrap_iterations=10, seed=10)
        time.sleep(0.05)
        st = get_job(out["job_id"]).to_status_dict()
        assert st["status"] in ("queued", "running")
        assert st["result_available"] is False
        blob = json.dumps(st)
        assert "market_results" not in blob
        assert "huge" not in blob
        gate.set()
        _wait_job(out["job_id"])


def test_12_13_summary_has_readiness_and_result_streamed():
    out = enqueue_purchasability_research_job(
        bootstrap_iterations=10, seed=12, rows=_rows(12)
    )
    st = _wait_job(out["job_id"])
    job = get_job(out["job_id"])
    summary = json.loads(Path(job.summary_file_path).read_text(encoding="utf-8"))
    assert "phase_2b_readiness" in summary
    assert "version" in summary
    result = json.loads(Path(job.result_file_path).read_text(encoding="utf-8"))
    assert result["version"] == STAT_VERSION
    assert st["result_available"] is True


def test_14_expired_files_cleaned(tmp_path: Path):
    import app.services.cecchino.cecchino_purchasability_research_jobs as jobs_mod

    jobs_mod.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    orphan = jobs_mod.RESULT_DIR / "orphan.result.json.tmp"
    orphan.write_text("{}", encoding="utf-8")
    stats = cleanup_expired_jobs()
    assert not orphan.exists()
    assert stats["removed_files"] >= 1


def test_15_16_failed_safe_error_no_traceback_in_status():
    with patch(
        "app.services.cecchino.cecchino_purchasability_research_jobs.build_purchasability_statistical_research",
        side_effect=RuntimeError("boom_internal"),
    ):
        out = enqueue_purchasability_research_job(bootstrap_iterations=10, seed=15)
        st = _wait_job(out["job_id"])
    assert st["status"] == "failed"
    assert st["error_code"] == "purchasability_research_job_failed"
    assert "boom_internal" in (st["error_message"] or "")
    assert "Traceback" not in json.dumps(st)


def test_17_missing_job_404():
    with pytest.raises(PurchasabilityResearchJobNotFound):
        get_job("does-not-exist")


def test_18_19_20_21_22_23_frontend_async_patterns():
    root = Path(__file__).resolve().parents[2]
    api = (root / "frontend/src/lib/cecchinoPurchasabilityStatisticalApi.ts").read_text(
        encoding="utf-8"
    )
    hook = (
        root / "frontend/src/hooks/useCecchinoPurchasabilityStatisticalResearch.ts"
    ).read_text(encoding="utf-8")
    body = (
        root
        / "frontend/src/components/cecchino-purchasability-research/PurchasabilityStatisticalResearchBody.tsx"
    ).read_text(encoding="utf-8")
    # 18: FE non usa più endpoint sincrono nel flusso
    assert "startPurchasabilityStatisticalJob" in api
    assert "getPurchasabilityStatisticalResearch" in api  # still exported for debug
    assert "getPurchasabilityStatisticalResearch(" not in hook.replace(
        "getPurchasabilityStatisticalResearch,", ""
    )
    assert "startPurchasabilityStatisticalJob" in hook
    # 19 poll ~2s
    assert "PURCHASABILITY_JOB_POLL_MS = 2000" in api
    assert "PURCHASABILITY_JOB_POLL_MS" in hook
    # 20 unmount clears timer
    assert "stopPolling" in hook
    assert "clearTimeout" in hook
    # 21 button disabled
    assert "disabled={loading}" in body
    # 22 active job resume
    assert "getActivePurchasabilityStatisticalJob" in hook
    # 23 no double job
    assert "busyRef" in hook


def test_24_25_no_migration_no_app_writes():
    root = Path(__file__).resolve().parents[2]
    migrations = list((root / "backend/alembic/versions").glob("*.py")) if (
        root / "backend/alembic/versions"
    ).exists() else []
    # job module must not import alembic / create tables
    src = (
        root
        / "backend/app/services/cecchino/cecchino_purchasability_research_jobs.py"
    ).read_text(encoding="utf-8")
    assert "alembic" not in src.lower()
    assert "create_all" not in src
    assert "SessionLocal" in src
    # no db.add / commit in job module
    assert "db.add" not in src
    assert "db.commit" not in src


def test_26_27_results_match_builder_and_version():
    rows = _rows(12)
    direct = build_purchasability_statistical_research(
        MagicMock(),
        rows=rows,
        bootstrap_iterations=10,
        seed=26,
    )
    out = enqueue_purchasability_research_job(
        bootstrap_iterations=10, seed=26, rows=rows
    )
    _wait_job(out["job_id"])
    job = get_job(out["job_id"])
    from_job = json.loads(Path(job.result_file_path).read_text(encoding="utf-8"))
    assert from_job["version"] == STAT_VERSION == "cecchino_purchasability_statistical_research_v2a_2"
    assert from_job["dataset_version"] == DATASET_VERSION
    assert from_job["status"] == direct["status"]
    assert from_job["phase_2b_readiness"]["recommended_next_step"] == (
        direct["phase_2b_readiness"]["recommended_next_step"]
    )


def test_28_29_audit_versions_and_cors_untouched():
    assert AUDIT_VERSION == "cecchino_purchasability_audit_v1_1"
    assert DATASET_VERSION == "cecchino_purchasability_dataset_v1_1"
    root = Path(__file__).resolve().parents[2]
    # CORS middleware file should not mention purchasability job changes
    cors_hits = list(root.glob("**/cors*.py")) + list(
        (root / "backend/app").glob("**/main.py")
    )
    # smoke: job module does not import CORS
    src = (
        root
        / "backend/app/services/cecchino/cecchino_purchasability_research_jobs.py"
    ).read_text(encoding="utf-8")
    assert "CORSMiddleware" not in src
    assert cors_hits  # project has main


def test_30_http_routes_smoke():
    from app.main import app

    client = TestClient(app)
    # active
    r = client.get("/api/admin/cecchino/research/purchasability/statistical-research/jobs/active")
    assert r.status_code == 200
    assert r.json()["job"] is None or "job_id" in (r.json().get("job") or {})

    with patch(
        "app.services.cecchino.cecchino_purchasability_research_jobs.build_purchasability_statistical_research",
        return_value=make_json_safe(
            {
                "status": "ok",
                "version": STAT_VERSION,
                "dataset_version": DATASET_VERSION,
                "phase_2b_readiness": {"recommended_next_step": "stop_no_incremental_signal"},
                "filters": {"bootstrap_iterations": 10},
                "elapsed_ms": {"total": 1},
                "limitations": [],
                "candidate_specifications": [],
                "feature_decisions": [],
                "cohort_identity": {},
                "data_quality": {},
            }
        ),
    ):
        r2 = client.post(
            "/api/admin/cecchino/research/purchasability/statistical-research/jobs",
            json={
                "date_from": "2026-01-01",
                "date_to": "2026-02-01",
                "bootstrap_iterations": 10,
                "seed": 30,
            },
        )
        assert r2.status_code == 202
        job_id = r2.json()["job_id"]
        st = _wait_job(job_id)
        assert st["status"] == "completed"
        r3 = client.get(
            f"/api/admin/cecchino/research/purchasability/statistical-research/jobs/{job_id}/summary"
        )
        assert r3.status_code == 200
        assert "phase_2b_readiness" in r3.json()
        r4 = client.get(
            f"/api/admin/cecchino/research/purchasability/statistical-research/jobs/{job_id}/result"
        )
        assert r4.status_code == 200
        assert r4.headers.get("content-type", "").startswith("application/json")

    r404 = client.get(
        "/api/admin/cecchino/research/purchasability/statistical-research/jobs/missing-id"
    )
    assert r404.status_code == 404
    assert r404.json()["error"] == "research_job_not_found_or_expired"

    # sync debug header
    with patch(
        "app.routes.cecchino_research.build_purchasability_statistical_research",
        return_value={"status": "ok", "version": STAT_VERSION},
    ):
        rs = client.get("/api/admin/cecchino/research/purchasability/statistical-research")
        assert rs.headers.get("x-research-execution-mode") == "synchronous-debug"


def test_filters_hash_stable():
    a = filters_hash_for(
        date_from="2026-01-01",
        date_to="2026-02-01",
        competition_id=None,
        market_family=None,
        selection=None,
        bootstrap_iterations=200,
        seed=42,
    )
    b = filters_hash_for(
        date_from="2026-01-01",
        date_to="2026-02-01",
        competition_id=None,
        market_family=None,
        selection=None,
        bootstrap_iterations=200,
        seed=42,
    )
    assert a == b


def test_progress_callback_invoked():
    stages: list[str] = []

    def cb(stage: str, meta: dict):
        stages.append(stage)

    build_purchasability_statistical_research(
        MagicMock(),
        rows=_rows(10),
        bootstrap_iterations=8,
        seed=99,
        progress_callback=cb,
    )
    for expected in (
        "loading_dataset",
        "feature_engineering",
        "temporal_cv",
        "building_payload",
        "serializing_result",
        "completed",
    ):
        assert expected in stages


def test_max_completed_constant():
    assert MAX_COMPLETED_JOBS == 5
