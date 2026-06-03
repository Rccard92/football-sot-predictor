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

CHUNK_DONE_PAYLOAD = {
    **DONE_PAYLOAD,
    "chunk": {"part": 1, "total_parts": 3, "round_from": 5, "round_to": 15},
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


def _fake_chunk_run(job_id: str) -> None:
    with _store_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "done"
        job.rows_expected = 110
        job.rows_done = 108
        job.progress_pct = 100.0
        job.round_from = 5
        job.round_to = 15
        job.chunk_part = 1
        job.chunk_total_parts = 3
        job.result_payload = CHUNK_DONE_PAYLOAD
        job.finished_at = "2026-01-01T00:00:00+00:00"


@patch(
    "app.services.backtest.v31_calibration_full_export_job._count_chunk_fixtures",
    return_value=2,
)
@patch(
    "app.services.backtest.v31_calibration_full_export_job._run_full_export_job",
    side_effect=_fake_run,
)
def test_full_export_job_lifecycle(mock_run, _mock_count):
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
    "app.services.backtest.v31_calibration_full_export_job._count_chunk_fixtures",
    return_value=2,
)
@patch(
    "app.services.backtest.v31_calibration_full_export_job._run_full_export_job",
    side_effect=_fake_run,
)
def test_full_export_job_cancel(mock_run, _mock_count):
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


@patch(
    "app.services.backtest.v31_calibration_full_export_job._count_chunk_fixtures",
    return_value=110,
)
@patch(
    "app.services.backtest.v31_calibration_full_export_job._run_full_export_job",
    side_effect=_fake_chunk_run,
)
def test_full_export_chunk_job(mock_run, mock_count):
    r = client.post(
        "/api/backtest/v31/calibration-dataset/full/build-job",
        params={
            "competition_id": 1,
            "season_year": 2025,
            "round_from": 5,
            "round_to": 15,
            "chunk_part": 1,
            "chunk_total_parts": 3,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["round_from"] == 5
    assert body["round_to"] == 15
    assert body["chunk_part"] == 1
    assert body["rows_expected"] == 110
    mock_count.assert_called_once()
    job_id = body["job_id"]

    status = client.get(f"/api/backtest/v31/calibration-dataset/full/build-job/{job_id}")
    assert status.json()["status"] == "done"

    dl = client.get(f"/api/backtest/v31/calibration-dataset/full/build-job/{job_id}/download")
    assert dl.status_code == 200
    assert dl.json()["chunk"]["part"] == 1
    disp = dl.headers.get("content-disposition", "")
    assert "part-1-rounds-5-15" in disp
    mock_run.assert_called_once()
