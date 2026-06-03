"""Test API job export JSON completo v3.1."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.backtest.v31_calibration_full_export_job import _jobs, _store_lock

client = TestClient(app)

DONE_PAYLOAD = {
    "report_type": "v31_calibration_dataset",
    "detail": "full",
    "fixtures_count": 2,
    "exportable": True,
    "anti_leakage_check": {"status": "ok", "forbidden_fields_found": []},
    "rows": [{"metadata": {"fixture_id": 1}, "features": {}, "target": {}, "comparisons": {}}],
}


def _fake_run(job_id: str) -> None:
    with _store_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "done"
        job.rows_expected = 2
        job.rows_done = 2
        job.progress_pct = 100.0
        job.result_payload = DONE_PAYLOAD
        job.finished_at = "2026-01-01T00:00:00+00:00"


@patch(
    "app.services.backtest.v31_calibration_full_export_job._run_full_export_job",
    side_effect=_fake_run,
)
def test_full_export_job_lifecycle(mock_run):
    r = client.post(
        "/api/backtest/v31/calibration-dataset/full/build-job",
        params={"competition_id": 1, "season_year": 2025},
    )
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    job_id = body["job_id"]

    status = client.get(f"/api/backtest/v31/calibration-dataset/full/build-job/{job_id}")
    assert status.status_code == 200
    st = status.json()
    assert st["status"] == "done"
    assert st["progress_pct"] == 100.0
    mock_run.assert_called_once()

    dl = client.get(f"/api/backtest/v31/calibration-dataset/full/build-job/{job_id}/download")
    assert dl.status_code == 200
    assert dl.json()["detail"] == "full"


@patch(
    "app.services.backtest.v31_calibration_full_export_job._run_full_export_job",
    side_effect=_fake_run,
)
def test_full_export_job_cancel(mock_run):
    r = client.post(
        "/api/backtest/v31/calibration-dataset/full/build-job",
        params={"competition_id": 1, "season_year": 2025},
    )
    job_id = r.json()["job_id"]
    cancel = client.post(f"/api/backtest/v31/calibration-dataset/full/build-job/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["job_id"] == job_id


def test_full_export_job_status_404():
    r = client.get("/api/backtest/v31/calibration-dataset/full/build-job/nonexistent-id")
    assert r.status_code == 404
