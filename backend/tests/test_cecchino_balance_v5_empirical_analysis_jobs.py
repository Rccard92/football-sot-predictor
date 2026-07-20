"""Regressione job analisi empirica Balance v5 Step 2B."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test_balance_emp_jobs",
)

from app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs import (
    BOOTSTRAP_ITERATIONS_DEFAULT,
    POLL_AFTER_MS,
    BalanceEmpiricalAnalysisJobConflict,
    BalanceEmpiricalAnalysisJobNotFound,
    enqueue_balance_empirical_analysis_job,
    get_balance_empirical_analysis_job,
    normalize_job_filters,
    reset_jobs_for_tests,
    set_result_dir_for_tests,
)


JOBS_PATH = "/api/cecchino/module-monitoring/balance-v5/empirical/analysis/jobs"


@pytest.fixture(autouse=True)
def _clean_jobs(tmp_path: Path):
    set_result_dir_for_tests(tmp_path / "bal_emp_jobs")
    reset_jobs_for_tests()
    yield
    reset_jobs_for_tests()


def _filters(**kwargs):
    base = {
        "date_from": "2024-01-01",
        "date_to": "2024-06-01",
        "competition_id": None,
        "source_cohort": "all",
        "bootstrap_iterations": BOOTSTRAP_ITERATIONS_DEFAULT,
    }
    base.update(kwargs)
    return normalize_job_filters(**base)


def _fake_analysis(**kwargs):
    return {
        "status": "ok",
        "bootstrap_iterations": kwargs.get("bootstrap_iterations", 2000),
        "overview": {
            "sample": {"settled": 10},
            "evidence_scope": "historical_diagnostic",
            "pillar_evidence_status": {
                "f36": {"status": "exploratory_evidence"},
                "dominance": {"status": "exploratory_evidence"},
                "draw_credibility": {"status": "exploratory_evidence"},
                "gap": {"status": "exploratory_evidence"},
            },
        },
    }


def _wait_status(job_id: str, want=("completed", "failed"), timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = get_balance_empirical_analysis_job(job_id)
        if st["status"] in want:
            return st
        time.sleep(0.05)
    raise AssertionError(
        f"timeout waiting for {want}: {get_balance_empirical_analysis_job(job_id)}"
    )


@pytest.fixture
def mock_db_and_build():
    with (
        patch(
            "app.core.database.SessionLocal",
            return_value=MagicMock(),
        ),
        patch(
            "app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs.build_balance_empirical_full_analysis",
            return_value=_fake_analysis(),
        ) as build,
    ):
        yield build


def test_normalize_bootstrap_bounds():
    assert _filters(bootstrap_iterations=500)["bootstrap_iterations"] == 500
    assert _filters(bootstrap_iterations=2000)["bootstrap_iterations"] == 2000
    assert _filters(bootstrap_iterations=10000)["bootstrap_iterations"] == 10000
    with pytest.raises(ValueError):
        _filters(bootstrap_iterations=100)
    with pytest.raises(ValueError):
        _filters(bootstrap_iterations=20000)


def test_enqueue_202_shape_and_poll(mock_db_and_build):
    out = enqueue_balance_empirical_analysis_job(_filters())
    assert out["status"] == "queued"
    assert "job_id" in out
    assert out["poll_after_ms"] == POLL_AFTER_MS
    st = _wait_status(out["job_id"])
    assert st["status"] == "completed"
    assert st["result"] is not None
    assert st["result"]["status"] == "ok"
    raw = json.dumps(st["result"], allow_nan=False)
    assert "NaN" not in raw


def test_conflict_409_different_filters_while_running():
    release = {"go": False}

    def slow_build(db, *, filters, bootstrap_iterations):
        while not release["go"]:
            time.sleep(0.02)
        return _fake_analysis(bootstrap_iterations=bootstrap_iterations)

    with (
        patch("app.core.database.SessionLocal", return_value=MagicMock()),
        patch(
            "app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs.build_balance_empirical_full_analysis",
            side_effect=slow_build,
        ),
    ):
        a = enqueue_balance_empirical_analysis_job(_filters(bootstrap_iterations=500))
        # attendi running
        t0 = time.time()
        while time.time() - t0 < 3:
            if get_balance_empirical_analysis_job(a["job_id"])["status"] == "running":
                break
            time.sleep(0.02)
        with pytest.raises(BalanceEmpiricalAnalysisJobConflict) as ei:
            enqueue_balance_empirical_analysis_job(
                _filters(bootstrap_iterations=2000, date_to="2024-07-01")
            )
        assert ei.value.active_job_id == a["job_id"]
        release["go"] = True
        _wait_status(a["job_id"])


def test_job_not_found():
    with pytest.raises(BalanceEmpiricalAnalysisJobNotFound):
        get_balance_empirical_analysis_job("missing-job-id")


def test_http_post_get_conflict_bootstrap_404():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    r_bad = client.post(
        JOBS_PATH,
        json={
            "date_from": "2024-01-01",
            "date_to": "2024-06-01",
            "bootstrap_iterations": 100,
        },
    )
    assert r_bad.status_code == 422

    r_bad2 = client.post(
        JOBS_PATH,
        json={
            "date_from": "2024-01-01",
            "date_to": "2024-06-01",
            "bootstrap_iterations": 15000,
        },
    )
    assert r_bad2.status_code == 422

    release = {"go": False}

    def slow_build(db, *, filters, bootstrap_iterations):
        while not release["go"]:
            time.sleep(0.02)
        return _fake_analysis(bootstrap_iterations=bootstrap_iterations)

    with (
        patch("app.core.database.SessionLocal", return_value=MagicMock()),
        patch(
            "app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs.build_balance_empirical_full_analysis",
            side_effect=slow_build,
        ),
    ):
        r = client.post(
            JOBS_PATH,
            json={
                "date_from": "2024-01-01",
                "date_to": "2024-06-01",
                "source_cohort": "all",
                "bootstrap_iterations": 2000,
            },
        )
        assert r.status_code == 202
        body = r.json()
        assert body["poll_after_ms"] == POLL_AFTER_MS
        job_id = body["job_id"]

        rg = client.get(f"{JOBS_PATH}/{job_id}")
        assert rg.status_code == 200
        assert rg.json()["status"] in ("queued", "running")

        # attendi running prima del 409
        t0 = time.time()
        while time.time() - t0 < 3:
            if client.get(f"{JOBS_PATH}/{job_id}").json()["status"] == "running":
                break
            time.sleep(0.02)

        r409 = client.post(
            JOBS_PATH,
            json={
                "date_from": "2024-02-01",
                "date_to": "2024-06-01",
                "bootstrap_iterations": 500,
            },
        )
        assert r409.status_code == 409
        detail = r409.json()["detail"]
        assert detail["error"] == "job_already_running"
        assert detail["active_job_id"] == job_id

        release["go"] = True

        t0 = time.time()
        st = None
        while time.time() - t0 < 5:
            st = client.get(f"{JOBS_PATH}/{job_id}").json()
            if st["status"] == "completed":
                break
            time.sleep(0.05)
        assert st is not None and st["status"] == "completed"
        assert st.get("result") is not None

    with (
        patch("app.core.database.SessionLocal", return_value=MagicMock()),
        patch(
            "app.services.cecchino.cecchino_balance_v5_empirical_analysis_jobs.build_balance_empirical_full_analysis",
            return_value=_fake_analysis(),
        ),
    ):
        for iters in (500, 2000, 10000):
            reset_jobs_for_tests()
            rx = client.post(
                JOBS_PATH,
                json={
                    "date_from": "2024-01-01",
                    "date_to": "2024-06-01",
                    "bootstrap_iterations": iters,
                },
            )
            assert rx.status_code == 202, iters
            jid = rx.json()["job_id"]
            t0 = time.time()
            s = None
            while time.time() - t0 < 5:
                s = client.get(f"{JOBS_PATH}/{jid}").json()
                if s["status"] in ("completed", "failed"):
                    break
                time.sleep(0.05)
            assert s is not None
            assert s["bootstrap_iterations"] == iters

    r404 = client.get(f"{JOBS_PATH}/does-not-exist")
    assert r404.status_code == 404
